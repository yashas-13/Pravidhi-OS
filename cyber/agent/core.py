"""Merged cybersecurity agent — VulnClaw engine + 817 Anthropic skills + Pravidhi infrastructure.

Architecture:
┌─────────────────────────────────────────────────────────────────────┐
│                      Pravidhi Cybersecurity Agent                    │
├─────────────────────────────────────────────────────────────────────┤
│  Input: Natural language pentest request                             │
│  Engine: VulnClaw OODA loop (Blackboard + Solver)                   │
│  Skills: 817 Anthropic Cybersecurity Skills (MITRE/NIST mapped)     │
│  Provider: OpenRouter (any model via 9router)                       │
│  Tools: MCP (fetch, nmap, python, chrome-devtools, burp)           │
│  Output: Structured report + PoC scripts                            │
└─────────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, TypeAlias

logger = logging.getLogger("pravidhi.cyber")


# ── Types ─────────────────────────────────────────────────────────────────────

class PentestPhase(str, Enum):
    RECON = "recon"
    DISCOVERY = "discovery"
    EXPLOITATION = "exploitation"
    PRIVESC = "privilege_escalation"
    PERSISTENCE = "persistence"
    REPORTING = "reporting"


@dataclass
class CyberTarget:
    url: str = ""
    ip: str = ""
    domain: str = ""
    format: str = "web"  # web | binary | network | cloud
    constraints: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CyberFinding:
    id: str = ""
    title: str = ""
    severity: str = "info"  # critical | high | medium | low | info
    phase: str = ""
    description: str = ""
    evidence: str = ""
    remediation: str = ""
    cve: str = ""
    mitre_id: str = ""
    skill_used: str = ""


@dataclass
class CyberReport:
    target: CyberTarget
    findings: List[CyberFinding] = field(default_factory=list)
    summary: str = ""
    poc_scripts: List[str] = field(default_factory=list)
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    status: str = "running"

    @property
    def duration(self) -> float:
        end = self.end_time or time.time()
        return end - self.start_time


# ── Cyber Skills Manager ─────────────────────────────────────────────────────

SKILLS_INDEX_URL = "https://raw.githubusercontent.com/mukul975/Anthropic-Cybersecurity-Skills/main/index.json"
SKILLS_DIR = Path.home() / ".pravidhi" / "cyber-skills"


class CyberSkillsManager:
    """Manages 817 Anthropic cybersecurity skills — discovery, loading, querying."""

    def __init__(self):
        self._skills: Dict[str, Dict[str, Any]] = {}
        self._loaded = False
        self._load()

    def _load(self) -> None:
        """Load skills index."""
        import httpx
        try:
            resp = httpx.get(SKILLS_INDEX_URL, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                for s in data.get("skills", []):
                    name = s.get("name", s.get("id", ""))
                    if name:
                        self._skills[name] = s
                self._loaded = True
                logger.info(f"Loaded {len(self._skills)} cybersecurity skills")
        except Exception as e:
            logger.warning(f"Failed to load skills index: {e}")
            # Try local cache
            local_idx = SKILLS_DIR / "index.json"
            if local_idx.exists():
                import json
                with open(local_idx) as f:
                    data = json.load(f)
                    for s in data.get("skills", []):
                        name = s.get("name", s.get("id", ""))
                        if name:
                            self._skills[name] = s
                    self._loaded = True
                    logger.info(f"Loaded {len(self._skills)} skills from local cache")

    async def get_skill_content(self, skill_name: str) -> Optional[str]:
        """Fetch a single skill's SKILL.md content."""
        if skill_name in self._skills:
            local_path = SKILLS_DIR / skill_name / "SKILL.md"
            if local_path.exists():
                return local_path.read_text()

            # Fetch from GitHub
            import httpx
            url = f"https://raw.githubusercontent.com/mukul975/Anthropic-Cybersecurity-Skills/main/skills/{skill_name}/SKILL.md"
            try:
                resp = await httpx.AsyncClient().get(url, timeout=10)
                if resp.status_code == 200:
                    (SKILLS_DIR / skill_name).mkdir(parents=True, exist_ok=True)
                    (SKILLS_DIR / skill_name / "SKILL.md").write_text(resp.text)
                    return resp.text
            except Exception:
                pass
        return None

    def search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """Search skills by name/description/tags."""
        query_lower = query.lower()
        scored = []
        for name, skill in self._skills.items():
            score = 0
            if query_lower in name.lower().replace('-', ' ').replace('_', ' '):
                score += 3
            desc = skill.get("description", "")
            if desc and query_lower in desc.lower():
                score += 2
            tags = skill.get("tools", []) + skill.get("techniques", []) + skill.get("frameworks", [])
            for t in tags:
                if query_lower in t.lower():
                    score += 1
            if score > 0:
                scored.append((score, {**skill, "id": name}))
        scored.sort(key=lambda x: -x[0])
        return [s for _, s in scored[:top_k]]

    def filter_by_mitre(self, technique_id: str) -> List[Dict[str, Any]]:
        """Filter skills by MITRE ATT&CK technique ID."""
        results = []
        for name, skill in self._skills.items():
            mappings = skill.get("mappings", []) or skill.get("frameworks", [])
            for m in mappings:
                if technique_id.upper() in m.upper():
                    results.append({**skill, "id": name})
                    break
        return results

    def filter_by_severity(self, severity: str) -> List[Dict[str, Any]]:
        """Filter skills by severity level."""
        results = []
        for name, skill in self._skills.items():
            if skill.get("severity", "").lower() == severity.lower():
                results.append({**skill, "id": name})
        return results

    @property
    def count(self) -> int:
        return len(self._skills)

    @property
    def categories(self) -> List[str]:
        cats = set()
        for s in self._skills.values():
            for t in s.get("tools", []):
                cats.add(t)
        return sorted(cats)


# ── VulnClaw Bridge ─────────────────────────────────────────────────────────

class VulnClawBridge:
    """Bridges Pravidhi with VulnClaw's OODA pentest engine."""

    def __init__(self, openrouter_key: str = ""):
        self.openrouter_key = openrouter_key or os.environ.get("OPENROUTER_API_KEY", "")
        self._agent = None
        self._config = None

    def configure(self, model: str = "openai/gpt-5.4-mini") -> None:
        """Configure VulnClaw for OpenRouter."""
        from vulnclaw.config.schema import VulnClawConfig
        from vulnclaw.config.settings import make_openai_client

        self._config = VulnClawConfig(
            llm={
                "provider": "openrouter",
                "model": model,
                "api_key": self.openrouter_key,
                "base_url": "https://openrouter.ai/api/v1",
                "max_context_tokens": 128000,
                "temperature": 0.3,
            },
            mcp_auto_approve=True,
            max_steps=100,
            sandbox_mode=False,
        )
        self._agent = None  # Will init on first run

    async def run_pentest(
        self,
        target: str,
        intent: str = "full pentest",
        model: str = "openai/gpt-5.4-mini",
    ) -> CyberReport:
        """Run a full penetration test against target."""
        from vulnclaw.agent.core import AgentCore
        from vulnclaw.agent.context import ContextManager, PentestPhase, SessionState
        from vulnclaw.agent.input_analysis import detect_target, detect_phase
        from vulnclaw.orchestrator import run_agent_task

        self.configure(model=model)
        report = CyberReport(target=CyberTarget(url=target))

        try:
            # Detect target type
            target_info = detect_target(target)
            report.target.ip = target_info.get("ip", "")
            report.target.domain = target_info.get("domain", "")
            report.target.format = target_info.get("type", "web")

            # Initialize agent
            agent = AgentCore(config=self._config)
            agent.context.state.target = target
            agent.context.state.phase = PentestPhase.RECON

            logger.info(f"Starting pentest: {target} (intent: {intent})")

            # Run the OODA loop
            result = await run_agent_task(
                agent=agent,
                command=intent,
                target=target,
                resume=False,
                runner=lambda a: self._run_agent_loop(a, intent),
            )

            # Extract findings
            for finding in agent.context.state.findings or []:
                report.findings.append(CyberFinding(
                    id=finding.get("id", ""),
                    title=finding.get("title", ""),
                    severity=finding.get("severity", "info"),
                    phase=finding.get("phase", ""),
                    description=finding.get("description", ""),
                    evidence=finding.get("evidence", ""),
                ))

            report.summary = f"Pentest completed: {len(report.findings)} findings"
            report.status = "completed"

        except Exception as e:
            logger.error(f"Pentest failed: {e}")
            report.status = "failed"
            report.summary = f"Error: {e}"

        report.end_time = time.time()
        return report

    async def run_single_command(
        self,
        target: str,
        command: str,
        model: str = "openai/gpt-5.4-mini",
    ) -> str:
        """Run a single pentest command (e.g. nmap scan, sqlmap)."""
        from vulnclaw.agent.core import AgentCore
        from vulnclaw.agent.llm_client import call_llm_auto
        from vulnclaw.agent.builtin_tools import execute_nmap, execute_python
        from vulnclaw.mcp.router import route_mcp_request

        self.configure(model=model)
        agent = AgentCore(config=self._config)

        # Execute the command directly using VulnClaw tools
        if "nmap" in command.lower():
            result = await execute_nmap(target, command)
            return str(result)
        elif "python" in command.lower() or "script" in command.lower():
            result = await execute_python(command)
            return str(result)
        elif "mcp" in command.lower() or "fetch" in command.lower():
            result = await route_mcp_request(command)
            return str(result)
        else:
            # Use LLM to interpret
            response = await call_llm_auto(
                agent=agent,
                messages=[{"role": "user", "content": f"Target: {target}\nCommand: {command}\nExecute this pentest command and return the result."}],
            )
            return response.get("content", str(response))

    async def _run_agent_loop(self, agent: Any, intent: str) -> Any:
        """Run the VulnClaw OODA agent loop."""
        from vulnclaw.agent.loop_controller import auto_pentest
        return await auto_pentest(agent, intent)


# ── Pravidhi Cyber Agent ────────────────────────────────────────────────────

class PravidhiCyberAgent:
    """Top-level cybersecurity agent that integrates everything."""

    def __init__(self, openrouter_key: str = ""):
        self.bridge = VulnClawBridge(openrouter_key)
        self.skills = CyberSkillsManager()
        self.report_store: List[CyberReport] = []

    async def pentest(
        self,
        target: str,
        intent: str = "full pentest",
        model: str = "openai/gpt-5.4-mini",
        use_skills: bool = True,
    ) -> CyberReport:
        """Run a penetration test with skill augmentation."""
        report = await self.bridge.run_pentest(target, intent, model)

        # Augment findings with relevant skills
        if use_skills:
            for finding in report.findings:
                relevant = self.skills.search(finding.title, top_k=3)
                if relevant:
                    finding.skill_used = relevant[0].get("id", "")

        self.report_store.append(report)
        return report

    async def scan(
        self,
        target: str,
        command: str = "nmap -sV",
        model: str = "openai/gpt-5.4-mini",
    ) -> str:
        """Run a single security command."""
        return await self.bridge.run_single_command(target, command, model)

    def search_skills(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """Search through 817 cybersecurity skills."""
        return self.skills.search(query, top_k)

    def get_skill_by_mitre(self, technique_id: str) -> List[Dict[str, Any]]:
        """Find skills mapped to a MITRE ATT&CK technique."""
        return self.skills.filter_by_mitre(technique_id)

    @property
    def total_skills(self) -> int:
        return self.skills.count


# Singleton
_cyber_agent: Optional[PravidhiCyberAgent] = None


def get_cyber_agent() -> PravidhiCyberAgent:
    global _cyber_agent
    if _cyber_agent is None:
        _cyber_agent = PravidhiCyberAgent()
    return _cyber_agent
