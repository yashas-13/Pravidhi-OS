"""Pravidhi Engine — core request lifecycle pipeline and registry.

The engine is the heart of Pravidhi:
1. Receives user requests through any transport
2. Validates, decomposes, routes, executes, and validates output
3. Learns from every interaction through the auto-research loop
4. Stores patterns in the experience database
"""

from engine.config import PravidhiConfig, get_config, load_config, reload_config
from engine.registry import Registry, get_registry, reset_registry
from engine.pipeline import Pipeline, PipelineContext
from engine.validator import ValidationEngine
from engine.provider_router import ProviderRouter
from engine.sandbox import CodeSandbox, SandboxConfig, SandboxBackend

__all__ = [
    "PravidhiConfig",
    "get_config",
    "load_config",
    "reload_config",
    "Registry",
    "get_registry",
    "reset_registry",
    "Pipeline",
    "PipelineContext",
    "ValidationEngine",
    "ProviderRouter",
    "CodeSandbox",
    "SandboxConfig",
    "SandboxBackend",
]
