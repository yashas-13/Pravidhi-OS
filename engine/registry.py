"""Unified registry for tools, MCP servers, skills, plugins, and hooks.

All discoverable capabilities register here — a single source of truth
for every extension point in Pravidhi.
"""

from __future__ import annotations

import importlib
import inspect
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol, TypeAlias

logger = logging.getLogger("pravidhi.registry")


# ── Type Aliases ──────────────────────────────────────────────────────────────

ToolHandler: TypeAlias = Callable[..., Any]
HookHandler: TypeAlias = Callable[..., Any]
SkillContent: TypeAlias = str


# ── Data Classes ──────────────────────────────────────────────────────────────

@dataclass
class ToolEntry:
    """Registered tool metadata."""
    name: str
    description: str
    schema: Dict[str, Any]
    handler: ToolHandler
    toolset: str = "default"
    source: str = "builtin"  # builtin | plugin | mcp | skill
    enabled: bool = True


@dataclass
class MCPServerEntry:
    """Registered MCP server."""
    name: str
    command: str
    args: List[str]
    tools: List[Dict[str, Any]] = field(default_factory=list)
    enabled: bool = True
    transport: str = "stdio"  # stdio | http


@dataclass
class SkillEntry:
    """Registered skill (knowledge document)."""
    name: str
    description: str
    content: SkillContent
    path: Optional[Path] = None
    source: str = "local"
    enabled: bool = True
    tags: List[str] = field(default_factory=list)


@dataclass
class PluginEntry:
    """Registered plugin."""
    name: str
    version: str
    description: str
    path: Path
    module: Any = None
    enabled: bool = True
    hooks: List[str] = field(default_factory=list)


@dataclass
class HookEntry:
    """Registered lifecycle hook."""
    name: str
    event: str  # pre_tool_call | post_tool_call | pre_execute | post_execute | on_error
    handler: HookHandler
    source: str = "builtin"
    priority: int = 100  # lower runs first


@dataclass
class ProviderEntry:
    """Registered model provider."""
    name: str
    api_type: str  # openai | anthropic | google | custom
    base_url: str
    models: List[str] = field(default_factory=list)
    credentials: List[str] = field(default_factory=list)
    priority: int = 100
    enabled: bool = True


# ── Registry ──────────────────────────────────────────────────────────────────

class Registry:
    """Unified capability registry — tools, MCP, skills, plugins, hooks."""

    def __init__(self):
        self.tools: Dict[str, ToolEntry] = {}
        self.mcp_servers: Dict[str, MCPServerEntry] = {}
        self.skills: Dict[str, SkillEntry] = {}
        self.plugins: Dict[str, PluginEntry] = {}
        self.hooks: Dict[str, List[HookEntry]] = {}
        self.providers: Dict[str, ProviderEntry] = {}

    # ── Tools ─────────────────────────────────────────────────────────────

    def register_tool(
        self,
        name: str,
        description: str,
        schema: Dict[str, Any],
        handler: ToolHandler,
        toolset: str = "default",
        source: str = "builtin",
    ) -> ToolEntry:
        entry = ToolEntry(
            name=name, description=description, schema=schema,
            handler=handler, toolset=toolset, source=source,
        )
        self.tools[name] = entry
        logger.debug(f"Registered tool: {name} (toolset={toolset}, source={source})")
        return entry

    def get_tool(self, name: str) -> Optional[ToolEntry]:
        return self.tools.get(name)

    def get_tools_by_toolset(self, toolset: str) -> List[ToolEntry]:
        return [t for t in self.tools.values() if t.toolset == toolset and t.enabled]

    def list_tools(self, enabled_only: bool = True) -> List[ToolEntry]:
        if enabled_only:
            return [t for t in self.tools.values() if t.enabled]
        return list(self.tools.values())

    # ── MCP Servers ────────────────────────────────────────────────────────

    def register_mcp_server(
        self,
        name: str,
        command: str,
        args: List[str],
        transport: str = "stdio",
    ) -> MCPServerEntry:
        entry = MCPServerEntry(
            name=name, command=command, args=args, transport=transport,
        )
        self.mcp_servers[name] = entry
        logger.debug(f"Registered MCP server: {name}")
        return entry

    def get_mcp_server(self, name: str) -> Optional[MCPServerEntry]:
        return self.mcp_servers.get(name)

    # ── Skills ─────────────────────────────────────────────────────────────

    def register_skill(
        self,
        name: str,
        description: str,
        content: SkillContent,
        path: Optional[Path] = None,
        tags: Optional[List[str]] = None,
    ) -> SkillEntry:
        entry = SkillEntry(
            name=name, description=description, content=content,
            path=path, tags=tags or [],
        )
        self.skills[name] = entry
        logger.debug(f"Registered skill: {name}")
        return entry

    def get_skill(self, name: str) -> Optional[SkillEntry]:
        return self.skills.get(name)

    def find_skills_by_tag(self, tag: str) -> List[SkillEntry]:
        return [s for s in self.skills.values() if tag in s.tags]

    # ── Plugins ────────────────────────────────────────────────────────────

    def register_plugin(
        self,
        name: str,
        version: str,
        description: str,
        path: Path,
    ) -> PluginEntry:
        entry = PluginEntry(
            name=name, version=version, description=description, path=path,
        )
        self.plugins[name] = entry
        logger.debug(f"Registered plugin: {name} v{version}")
        return entry

    def get_plugin(self, name: str) -> Optional[PluginEntry]:
        return self.plugins.get(name)

    # ── Hooks ──────────────────────────────────────────────────────────────

    def register_hook(
        self,
        name: str,
        event: str,
        handler: HookHandler,
        source: str = "builtin",
        priority: int = 100,
    ) -> HookEntry:
        entry = HookEntry(
            name=name, event=event, handler=handler,
            source=source, priority=priority,
        )
        self.hooks.setdefault(event, []).append(entry)
        self.hooks[event].sort(key=lambda h: h.priority)
        logger.debug(f"Registered hook: {name} → event={event}")
        return entry

    def get_hooks(self, event: str) -> List[HookEntry]:
        return self.hooks.get(event, [])

    def trigger_hooks(self, event: str, **context: Any) -> None:
        """Run all hooks for an event, catching errors."""
        for hook in self.get_hooks(event):
            try:
                result = hook.handler(**context)
                if inspect.iscoroutine(result):
                    import asyncio
                    asyncio.create_task(result)
            except Exception as e:
                logger.warning(f"Hook '{hook.name}' failed on event '{event}': {e}")

    # ── Providers ──────────────────────────────────────────────────────────

    def register_provider(
        self,
        name: str,
        api_type: str,
        base_url: str,
        models: Optional[List[str]] = None,
        priority: int = 100,
    ) -> ProviderEntry:
        entry = ProviderEntry(
            name=name, api_type=api_type, base_url=base_url,
            models=models or [], priority=priority,
        )
        self.providers[name] = entry
        logger.debug(f"Registered provider: {name} ({api_type})")
        return entry

    def get_provider(self, name: str) -> Optional[ProviderEntry]:
        return self.providers.get(name)

    def list_providers(self, enabled_only: bool = True) -> List[ProviderEntry]:
        if enabled_only:
            return [p for p in self.providers.values() if p.enabled]
        return list(self.providers.values())

    # ── Discovery ──────────────────────────────────────────────────────────

    def discover_skills(self, skill_dirs: Optional[List[Path]] = None) -> int:
        """Scan directories for skill files and auto-register."""
        if skill_dirs is None:
            skill_dirs = [
                Path.home() / ".codex" / "skills",
                Path.home() / ".pravidhi" / "skills",
                Path.cwd() / "skills",
            ]
        count = 0
        for d in skill_dirs:
            if not d.exists():
                continue
            for item in d.iterdir():
                if item.is_dir() and (item / "SKILL.md").exists():
                    content = (item / "SKILL.md").read_text()
                    name = item.name
                    desc = ""
                    for line in content.splitlines():
                        if line.startswith("description:"):
                            desc = line.split(":", 1)[1].strip().strip('"')
                            break
                    self.register_skill(name, desc, content, path=item)
                    count += 1
        logger.info(f"Discovered {count} skills")
        return count

    def discover_plugins(self, plugin_dirs: Optional[List[Path]] = None) -> int:
        """Scan directories for plugins and auto-register."""
        if plugin_dirs is None:
            plugin_dirs = [
                Path.home() / ".pravidhi" / "plugins",
            ]
        count = 0
        for d in plugin_dirs:
            if not d.exists():
                continue
            for item in d.iterdir():
                manifest = item / "plugin.yaml"
                if manifest.exists():
                    import yaml
                    with open(manifest) as f:
                        meta = yaml.safe_load(f)
                    if meta:
                        self.register_plugin(
                            name=meta.get("name", item.name),
                            version=meta.get("version", "0.1"),
                            description=meta.get("description", ""),
                            path=item,
                        )
                        count += 1
        logger.info(f"Discovered {count} plugins")
        return count

    def summary(self) -> Dict[str, int]:
        return {
            "tools": len(self.list_tools()),
            "mcp_servers": len(self.mcp_servers),
            "skills": len(self.skills),
            "plugins": len(self.plugins),
            "hooks": sum(len(v) for v in self.hooks.values()),
            "providers": len(self.list_providers()),
        }


# Global registry singleton
_registry: Optional[Registry] = None


def get_registry() -> Registry:
    global _registry
    if _registry is None:
        _registry = Registry()
    return _registry


def reset_registry() -> None:
    global _registry
    _registry = Registry()
