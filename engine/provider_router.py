"""Multi-model provider router with credential pooling and automatic fallback.

Inspired by Hermes Agent's provider routing system with:
- Smart sorting by price/throughput/latency
- Credential pools with automatic rotation
- Cascading fallback chain
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TypeAlias

import httpx

from engine.config import get_config

logger = logging.getLogger("pravidhi.provider_router")


# ── Types ─────────────────────────────────────────────────────────────────────

ChatMessage: TypeAlias = Dict[str, str]  # {"role": ..., "content": ...}


@dataclass
class Credential:
    """A single API key or OAuth token for a provider."""
    key: str
    source: str = "env"  # env | manual | oauth
    cooldown_until: float = 0.0
    errors: int = 0


@dataclass
class ProviderEndpoint:
    """A provider + model endpoint that can handle requests."""
    provider: str
    model: str
    api_type: str = "openai"
    base_url: str = ""
    credentials: List[Credential] = field(default_factory=list)
    priority: int = 100
    price_per_mtok: float = 0.0
    latency_p50_ms: float = 0.0
    throughput_tok_s: float = 0.0


# ── Built-in Provider Definitions ─────────────────────────────────────────────

BUILTIN_PROVIDERS = {
    "openai": {
        "api_type": "openai",
        "base_url": "https://api.openai.com/v1",
        "env_key": "OPENAI_API_KEY",
        "models": {
            "gpt-5.4-mini": {"price": 0.15, "latency": 800, "throughput": 200},
            "gpt-5.5": {"price": 2.50, "latency": 1200, "throughput": 150},
        },
    },
    "openrouter": {
        "api_type": "openai",
        "base_url": "https://openrouter.ai/api/v1",
        "env_key": "OPENROUTER_API_KEY",
        "models": {
            "anthropic/claude-sonnet-4.6": {"price": 3.00, "latency": 1500, "throughput": 120},
            "openai/gpt-5.4-mini": {"price": 0.15, "latency": 800, "throughput": 200},
        },
    },
    "anthropic": {
        "api_type": "anthropic",
        "base_url": "https://api.anthropic.com/v1",
        "env_key": "ANTHROPIC_API_KEY",
        "models": {
            "claude-sonnet-4.6": {"price": 3.00, "latency": 1500, "throughput": 120},
        },
    },
    "gemini": {
        "api_type": "openai",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "env_key": "GEMINI_API_KEY",
        "models": {
            "gemini-2.5-flash": {"price": 0.15, "latency": 500, "throughput": 300},
        },
    },
}


# ── Provider Router ───────────────────────────────────────────────────────────

class ProviderRouter:
    """Routes requests to the best provider based on configurable strategy."""

    def __init__(self):
        self.config = get_config().providers
        self.endpoints: Dict[str, ProviderEndpoint] = {}
        self._init_endpoints()

    def _init_endpoints(self) -> None:
        """Build endpoint list from config and env vars."""
        for name, info in BUILTIN_PROVIDERS.items():
            key = self._resolve_credential(info.get("env_key", ""))
            creds = [Credential(key=key, source="env")] if key else []

            for model_name, perf in info["models"].items():
                ep = ProviderEndpoint(
                    provider=name,
                    model=model_name,
                    api_type=info["api_type"],
                    base_url=info["base_url"],
                    credentials=creds,
                    price_per_mtok=perf["price"],
                    latency_p50_ms=perf["latency"],
                    throughput_tok_s=perf["throughput"],
                )
                self.endpoints[f"{name}/{model_name}"] = ep

    def _resolve_credential(self, env_key: str) -> str:
        """Resolve credential from env, config, or .env file."""
        # Check direct env var
        val = os.getenv(env_key)
        if val:
            return val

        # Check config credentials dict
        cred_key = env_key.lower().replace("_api_key", "").replace("_key", "").lower()
        creds = self.config.credentials
        if cred_key in creds:
            return os.path.expandvars(creds[cred_key])

        # Check .env file
        try:
            from dotenv import load_dotenv
            load_dotenv()
            return os.getenv(env_key, "")
        except ImportError:
            return ""

    async def select(
        self, intent: Optional[Dict[str, Any]] = None
    ) -> Dict[str, str]:
        """Select the best provider:model pair based on routing config."""
        available = [ep for ep in self.endpoints.values() if ep.credentials and ep.credentials[0].key]
        if not available:
            return {"provider": "openai", "model": "gpt-5.4-mini"}

        routing = self.config.routing

        # Apply whitelist
        if routing.only:
            available = [ep for ep in available if ep.provider in routing.only]

        # Apply blacklist
        if routing.ignore:
            available = [ep for ep in available if ep.provider not in routing.ignore]

        # Apply priority order
        if routing.order:
            ordered = []
            for provider_name in routing.order:
                for ep in available:
                    if ep.provider == provider_name:
                        ordered.append(ep)
            remaining = [ep for ep in available if ep.provider not in routing.order]
            available = ordered + remaining

        # Sort by strategy
        sort_key = routing.sort
        if sort_key == "price":
            available.sort(key=lambda ep: ep.price_per_mtok)
        elif sort_key == "latency":
            available.sort(key=lambda ep: ep.latency_p50_ms)
        elif sort_key == "throughput":
            available.sort(key=lambda ep: -ep.throughput_tok_s)

        best = available[0]
        return {
            "provider": best.provider,
            "model": best.model,
            "api_type": best.api_type,
            "base_url": best.base_url,
        }

    async def chat(
        self,
        messages: List[ChatMessage],
        model: Optional[str] = None,
        provider: Optional[str] = None,
        max_retries: int = 3,
    ) -> Dict[str, Any]:
        """Send a chat request to the selected provider with fallback."""
        ep = self._find_endpoint(provider or "openai", model or self.config.default_model)
        if not ep:
            logger.error(f"No endpoint for {provider}/{model}")
            return {"error": "No available endpoint", "content": ""}

        credential = self._get_credential(ep)
        if not credential:
            return {"error": f"No credential for {ep.provider}", "content": ""}

        last_error = ""
        for attempt in range(max_retries):
            try:
                return await self._call_api(ep, credential, messages)
            except Exception as e:
                last_error = str(e)
                logger.warning(f"Attempt {attempt + 1} failed for {ep.provider}/{ep.model}: {e}")
                credential.errors += 1

                # Try fallback
                if attempt < max_retries - 1:
                    fallback = await self._get_fallback(ep)
                    if fallback:
                        ep = fallback
                        credential = self._get_credential(ep)
                        continue

                await asyncio.sleep(1 * (attempt + 1))

        return {"error": f"All retries failed: {last_error}", "content": ""}

    async def _call_api(
        self, ep: ProviderEndpoint, credential: Credential, messages: List[ChatMessage]
    ) -> Dict[str, Any]:
        """Make the actual HTTP call to the LLM API."""
        headers = {"Content-Type": "application/json"}

        if ep.api_type == "openai":
            headers["Authorization"] = f"Bearer {credential.key}"
        elif ep.api_type == "anthropic":
            headers["x-api-key"] = credential.key
            headers["anthropic-version"] = "2023-06-01"

        payload = {
            "model": ep.model,
            "messages": messages,
            "max_tokens": 1_000_000,
            "temperature": 0.7,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            url = f"{ep.base_url}/chat/completions"
            if ep.api_type == "anthropic":
                url = f"{ep.base_url}/messages"
                payload.pop("max_tokens", None)
                payload["max_tokens"] = 1_000_000

            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

            if ep.api_type == "anthropic":
                return {
                    "content": data.get("content", [{}])[0].get("text", ""),
                    "model": data.get("model", ep.model),
                    "usage": data.get("usage", {}),
                    "provider": ep.provider,
                }

            return {
                "content": data.get("choices", [{}])[0].get("message", {}).get("content", ""),
                "model": data.get("model", ep.model),
                "usage": data.get("usage", {}),
                "provider": ep.provider,
            }

    def _find_endpoint(self, provider: str, model: str) -> Optional[ProviderEndpoint]:
        key = f"{provider}/{model}"
        if key in self.endpoints:
            return self.endpoints[key]
        # Try prefix match
        for k, ep in self.endpoints.items():
            if ep.provider == provider and model in k:
                return ep
        return None

    def _get_credential(self, ep: ProviderEndpoint) -> Optional[Credential]:
        """Get next healthy credential from pool."""
        strategy = self.config.credential_pools.strategy
        healthy = [c for c in ep.credentials if c.cooldown_until < asyncio.get_event_loop().time()]

        if not healthy:
            return None

        if strategy == "round_robin":
            return healthy[0]
        elif strategy == "least_used":
            return min(healthy, key=lambda c: c.errors)
        elif strategy == "random":
            return random.choice(healthy)

        return healthy[0]

    async def _get_fallback(self, current: ProviderEndpoint) -> Optional[ProviderEndpoint]:
        """Find a fallback endpoint from a different provider."""
        if not self.config.fallback.enabled:
            return None

        for ep in sorted(self.endpoints.values(), key=lambda e: e.priority):
            if ep.provider != current.provider and ep.credentials and ep.credentials[0].key:
                logger.info(f"Falling back to {ep.provider}/{ep.model}")
                return ep
        return None
