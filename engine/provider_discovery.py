"""Provider auto-discovery engine — finds OpenCode/9router/local endpoints and auto-rotates models.

Auto-detects:
- OpenCode compatible endpoints at localhost:20128/v1
- 9Router at localhost:20128/v1 (OpenRouter-compatible)
- Any OpenAI-compatible local endpoint
- Built-in providers (OpenAI, OpenRouter, Anthropic, Gemini)

Auto-rotate: when a model is exhausted/rate-limited, seamlessly switches to the next.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

import httpx

logger = logging.getLogger("pravidhi.provider_discovery")


# ── Types ─────────────────────────────────────────────────────────────────────

@dataclass
class DiscoveredModel:
    """A model discovered on a local/remote endpoint."""
    id: str
    provider: str
    base_url: str
    api_type: str = "openai"
    available: bool = True
    latency_ms: float = 0.0
    last_used: float = 0.0
    error_count: int = 0
    cooldown_until: float = 0.0  # timestamp when cooldown ends


@dataclass
class ProviderEndpoint:
    """A discovered API endpoint."""
    name: str
    base_url: str
    api_type: str = "openai"
    models: List[str] = field(default_factory=list)
    healthy: bool = True
    requires_key: bool = False
    key_env_var: str = ""


# ── Discovery Engine ──────────────────────────────────────────────────────────

LOCAL_ENDPOINTS = [
    {"name": "opencode", "url": "http://localhost:20128/v1", "api_type": "openai"},
    {"name": "9router", "url": "http://localhost:20128/v1", "api_type": "openai"},
    {"name": "local-ollama", "url": "http://localhost:11434/v1", "api_type": "openai"},
    {"name": "local-vllm", "url": "http://localhost:8000/v1", "api_type": "openai"},
    {"name": "local-tgi", "url": "http://localhost:8080/v1", "api_type": "openai"},
    {"name": "local-lmstudio", "url": "http://localhost:1234/v1", "api_type": "openai"},
]

ENDPOINT_WELL_KNOWN_PATHS = ["/v1/models", "/models", "/api/models", "/health"]


class ProviderDiscovery:
    """Discovers and manages model providers with auto-rotation."""

    def __init__(self):
        self.discovered: Dict[str, DiscoveredModel] = {}
        self.endpoints: Dict[str, ProviderEndpoint] = {}
        self._model_index: List[str] = []  # Ordered list for rotation
        self._current_idx: int = 0
        self._lock = asyncio.Lock()

        # Start with built-in providers
        self._load_builtin()

    def _load_builtin(self):
        """Load built-in provider definitions."""
        from engine.provider_router import BUILTIN_PROVIDERS
        for name, info in BUILTIN_PROVIDERS.items():
            key = os.getenv(info.get("env_key", ""), "")
            ep = ProviderEndpoint(
                name=name,
                base_url=info["base_url"],
                api_type=info["api_type"],
                models=list(info["models"].keys()),
                requires_key=True,
                key_env_var=info.get("env_key", ""),
                healthy=bool(key),
            )
            self.endpoints[name] = ep
            for model_name in info["models"]:
                mid = f"{name}/{model_name}"
                self.discovered[mid] = DiscoveredModel(
                    id=mid, provider=name,
                    base_url=ep.base_url, api_type=ep.api_type,
                    available=bool(key),
                )
                self._model_index.append(mid)

    async def discover_local(self) -> int:
        """Scan localhost for OpenAI-compatible endpoints and their models."""
        count = 0
        async with httpx.AsyncClient(timeout=3.0) as client:
            for ep_def in LOCAL_ENDPOINTS:
                name = ep_def["name"]
                base_url = ep_def["url"]
                try:
                    # Try to fetch model list
                    models = await self._fetch_models(client, base_url)
                    if models:
                        ep = ProviderEndpoint(
                            name=name,
                            base_url=base_url,
                            api_type=ep_def["api_type"],
                            models=models,
                            healthy=True,
                        )
                        self.endpoints[name] = ep
                        for model_id in models:
                            mid = f"{name}/{model_id}"
                            if mid not in self.discovered:
                                self.discovered[mid] = DiscoveredModel(
                                    id=mid, provider=name,
                                    base_url=base_url,
                                    api_type=ep_def["api_type"],
                                    available=True,
                                )
                                self._model_index.append(mid)
                                count += 1
                        logger.info(f"Discovered {name} at {base_url}: {len(models)} models")
                except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError):
                    logger.debug(f"No {name} endpoint at {base_url}")
                except Exception as e:
                    logger.debug(f"Discovery error for {name}: {e}")
        return count

    async def _fetch_models(self, client: httpx.AsyncClient, base_url: str) -> Optional[List[str]]:
        """Fetch model list from an OpenAI-compatible endpoint."""
        for path in ENDPOINT_WELL_KNOWN_PATHS:
            try:
                url = base_url.rstrip("/") + path
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    models = []
                    # OpenAI format: {"data": [{"id": "..."}]}
                    if "data" in data and isinstance(data["data"], list):
                        models = [m["id"] for m in data["data"] if "id" in m]
                    # Simple list
                    elif isinstance(data, list):
                        models = [m if isinstance(m, str) else m.get("id", "") for m in data]
                    # Dict with model keys
                    elif isinstance(data, dict):
                        models = list(data.keys())
                    if models:
                        return models
            except Exception:
                continue
        return None

    async def check_endpoint_health(self, base_url: str) -> Tuple[bool, float]:
        """Check if an endpoint is healthy and measure latency."""
        start = time.time()
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(f"{base_url.rstrip('/')}/models")
                latency = (time.time() - start) * 1000
                return resp.status_code == 200, latency
        except Exception:
            return False, 0.0

    async def select_model(self, preferred: Optional[str] = None,
                            exclude: Optional[Set[str]] = None) -> Optional[DiscoveredModel]:
        """Select a model for use, with auto-rotation on failure.

        Strategy:
        1. Try preferred model
        2. If preferred is exhausted/cooldown, rotate to next available
        3. Skip models in cooldown
        4. Cycle through all discovered models
        """
        exclude = exclude or set()
        available = [
            m for m in self.discovered.values()
            if m.available
            and m.id not in exclude
            and time.time() >= m.cooldown_until
            and m.error_count < 3  # Max 3 errors before cooling
        ]

        if not available:
            logger.warning("No available models — all exhausted or in cooldown")
            # Reset cooldowns as last resort
            for m in self.discovered.values():
                m.cooldown_until = 0
                m.error_count = 0
            available = [m for m in self.discovered.values() if m.available]

        # Preferred model
        if preferred:
            for m in available:
                if m.id == preferred or m.id.endswith(preferred):
                    return m

        # Rotate through available models
        if available:
            # Sort by error count (fewest first), then by latency
            available.sort(key=lambda m: (m.error_count, m.latency_ms))
            selected = available[0]
            # Update rotation index
            self._current_idx = (self._current_idx + 1) % max(len(self._model_index), 1)
            return selected

        return None

    async def report_failure(self, model_id: str):
        """Report a model failure — triggers cooldown and rotation."""
        async with self._lock:
            if model_id in self.discovered:
                m = self.discovered[model_id]
                m.error_count += 1
                m.cooldown_until = time.time() + (30 * m.error_count)  # Exponential backoff
                logger.info(f"Model {model_id} failed ({m.error_count}x). Cooldown until {m.cooldown_until:.0f}")

                # If too many errors, deprioritize
                if m.error_count >= 5:
                    m.available = False
                    logger.warning(f"Model {model_id} disabled after {m.error_count} failures")

    async def report_success(self, model_id: str, latency_ms: float = 0):
        """Report successful model usage."""
        async with self._lock:
            if model_id in self.discovered:
                m = self.discovered[model_id]
                m.error_count = max(0, m.error_count - 1)  # Decrement error count
                m.last_used = time.time()
                if latency_ms > 0:
                    # Moving average
                    m.latency_ms = (m.latency_ms * 0.7) + (latency_ms * 0.3)
                m.available = True
                m.cooldown_until = 0

    def get_status(self) -> Dict[str, Any]:
        """Get full status of all providers and models."""
        providers = {}
        for name, ep in self.endpoints.items():
            providers[name] = {
                "name": name,
                "base_url": ep.base_url,
                "healthy": ep.healthy,
                "requires_key": ep.requires_key,
                "key_configured": bool(os.getenv(ep.key_env_var, "")) if ep.requires_key else True,
                "models": ep.models,
            }

        models = {}
        for mid, m in self.discovered.items():
            models[mid] = {
                "id": mid,
                "provider": m.provider,
                "available": m.available,
                "latency_ms": round(m.latency_ms, 1),
                "error_count": m.error_count,
                "on_cooldown": time.time() < m.cooldown_until,
                "cooldown_remaining": max(0, round(m.cooldown_until - time.time(), 1)) if time.time() < m.cooldown_until else 0,
            }

        return {
            "providers": providers,
            "models": models,
            "total_models": len(self.discovered),
            "available_models": sum(1 for m in self.discovered.values() if m.available),
            "rotation_index": self._current_idx,
        }

    def get_available_models(self) -> List[str]:
        """Get sorted list of available model IDs."""
        available = [
            m for m in self.discovered.values()
            if m.available and time.time() >= m.cooldown_until
        ]
        available.sort(key=lambda m: (m.error_count, m.latency_ms))
        return [m.id for m in available]

    async def auto_rotate_chat(self, preferred: Optional[str] = None) -> Tuple[Optional[DiscoveredModel], Dict[str, Any]]:
        """Select a model with full trace info for the UI."""
        model = await self.select_model(preferred)
        status = self.get_status()
        return model, status


# ── Global singleton ──────────────────────────────────────────────────────────

_discovery: Optional[ProviderDiscovery] = None


def get_discovery() -> ProviderDiscovery:
    global _discovery
    if _discovery is None:
        _discovery = ProviderDiscovery()
    return _discovery


async def discover_all() -> Dict[str, Any]:
    """Run full discovery and return status."""
    d = get_discovery()
    local_count = await d.discover_local()
    return {"discovered_local": local_count, "status": d.get_status()}
