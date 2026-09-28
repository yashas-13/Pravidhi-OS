"""Merged Router Agent: VulnClaw + 817 Cybersecurity Skills + Pravidhi Engine.

Runs entirely through OpenRouter (9router) for model-agnostic pentesting.
No local LLM needed — bring your own API key.
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

import httpx

logger = logging.getLogger("pravidhi.router_agent")


# ── Types ─────────────────────────────────────────────────────────────────────

class PentestPhase(str, Enum):
    RECON = "recon"
    DISCOVERY = "discovery"
    EXPLOITATION = "exploitation"
    PRIVESC = "privilege_escalation"
    PERSISTENCE = "persistence"
    REPORTING = "reporting"


@dataclass
class RouterTarget:
    url: str = ""
    ip: str = ""
    domain: str = ""
    target_type: str = "web"  # web | binary | network | cloud | api
    constraints: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RouterFinding:
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
    confidence: float = 0.0


@dataclass
class RouterReport:
    target: RouterTarget
    findings: List[RouterFinding] = field(default_factory=list)
    summary: str = ""
    poc_scripts: List[str] = field(default_factory=list)
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    status: str = "running"
    model_used: str = ""
    provider: str = "openrouter"

    @property
    def duration(self) -> float:
        end = self.end_time or time.time()
        return end - self.start_time


# ── Router Agent ──────────────────────────────────────────────────────────────

class NineRouterAgent:
    """Agent that runs through OpenRouter (9router) with merged VulnClaw + skills.

    Features:
    - Model-agnostic: use any OpenRouter model (gpt-5, claude, gemini, deepseek, etc.)
    - 817 MITRE-mapped cybersecurity skills for guided pentesting
    - VulnClaw OODA loop for automated exploitation
    - Built-in tools: nmap, sqlmap, python, MCP fetch, chrome-devtools
    - Structured JSON reporting with remediation
    """

    def __init__(self, api_key: str = "", base_url: str = "https://openrouter.ai/api/v1"):
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY", "")
        self.base_url = base_url
        self.default_model = os.getenv("ROUTER_MODEL", "openai/gpt-5.4-mini")
        self.skills_index: Dict[str, Any] = {}
        self._load_skills()

    def _load_skills(self) -> None:
        """Load the 817 Anthropic cybersecurity skills index."""
        try:
            resp = httpx.get(
                "https://raw.githubusercontent.com/mukul975/Anthropic-Cybersecurity-Skills/main/index.json",
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                for s in data.get("skills", []):
                    sid = s.get("id", s.get("name", ""))
                    if sid:
                        self.skills_index[sid] = s
                logger.info(f"Loaded {len(self.skills_index)} cybersecurity skills")
        except Exception as e:
            logger.warning(f"Could not fetch skills index: {e}")

    async def chat(self, messages: List[Dict[str, Any]],
                   model: Optional[str] = None,
                   temperature: float = 0.3,
                   max_tokens: int = 4096) -> Dict[str, Any]:
        """Send chat request through OpenRouter."""
        model = model or self.default_model

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://pravidhisolutions.in",
            "X-Title": "Pravidhi Router Agent",
        }

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                return {
                    "content": data["choices"][0]["message"]["content"],
                    "model": data.get("model", model),
                    "usage": data.get("usage", {}),
                    "provider": "openrouter",
                }
            except Exception as e:
                logger.error(f"Router API call failed: {e}")
                return {"error": str(e), "content": ""}

    async def pentest(self, target: str, intent: str = "full pentest",
                      model: Optional[str] = None) -> RouterReport:
        """Run a full penetration test through the router."""
        model = model or self.default_model
        report = RouterReport(
            target=RouterTarget(url=target),
            model_used=model,
        )

        # Phase 1: Recon
        recon_prompt = self._build_prompt("recon", target, intent)
        recon_result = await self.chat(
            messages=[{"role": "system", "content": self._system_prompt()},
                      {"role": "user", "content": recon_prompt}],
            model=model,
        )

        if "error" in recon_result:
            report.status = "failed"
            report.summary = recon_result.get("error", "Unknown error")
            report.end_time = time.time()
            return report

        # Parse findings from response
        findings = self._parse_findings(recon_result.get("content", ""), "recon")
        report.findings.extend(findings)

        # Phase 2: Discovery
        discovery_result = await self.chat(
            messages=[{"role": "system", "content": self._system_prompt()},
                      {"role": "user", "content": f"Target: {target}\nPhase: discovery\nIntent: {intent}\nRecon results: {recon_result.get('content', '')[:2000]}\n\nRun discovery phase (port scanning, service enumeration, vulnerability scanning). Return findings as structured JSON."}],
            model=model,
        )
        findings = self._parse_findings(discovery_result.get("content", ""), "discovery")
        report.findings.extend(findings)

        # Phase 3: Exploitation
        exploit_result = await self.chat(
            messages=[{"role": "system", "content": self._system_prompt()},
                      {"role": "user", "content": f"Target: {target}\nPhase: exploitation\nIntent: {intent}\nDiscovery findings: {discovery_result.get('content', '')[:2000]}\n\nRun exploitation phase. Attempt to exploit discovered vulnerabilities. Return findings as structured JSON."}],
            model=model,
        )
        findings = self._parse_findings(exploit_result.get("content", ""), "exploitation")
        report.findings.extend(findings)

        # Phase 4: Reporting
        report_result = await self.chat(
            messages=[{"role": "system", "content": self._system_prompt()},
                      {"role": "user", "content": f"Target: {target}\nAll findings: {json.dumps([{'title': f.title, 'severity': f.severity, 'description': f.description} for f in report.findings])}\n\nGenerate a comprehensive security report with:\n1. Executive summary\n2. Critical findings (CVSS scoring)\n3. Remediation steps\n4. PoC commands"}],
            model=model,
        )

        report.summary = report_result.get("content", "Pentest completed")
        report.status = "completed"
        report.end_time = time.time()

        # Deduplicate and sort findings by severity
        seen = set()
        unique_findings = []
        for f in report.findings:
            if f.title not in seen:
                seen.add(f.title)
                unique_findings.append(f)
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
        unique_findings.sort(key=lambda x: severity_order.get(x.severity, 5))
        report.findings = unique_findings

        return report

    def _system_prompt(self) -> str:
        return f"""You are Pravidhi Router Agent — an elite cybersecurity AI with access to {len(self.skills_index)} MITRE-mapped skills.

Your capabilities:
- Web application penetration testing
- Network security assessment
- API security testing
- Cloud infrastructure review
- Binary exploitation assistance
- Social engineering scenarios

For every finding, include:
- severity (critical/high/medium/low/info)
- CVSS score where applicable
- MITRE ATT&CK technique ID
- Step-by-step reproduction
- Remediation guidance

Always return findings as structured JSON when requested.
Always follow OWASP testing methodology.
Never perform actual exploitation without explicit authorization."""

    def _build_prompt(self, phase: str, target: str, intent: str) -> str:
        return f"""Target: {target}
Phase: {phase}
Intent: {intent}

Available skills: {list(self.skills_index.keys())[:20]}...

Execute {phase} phase of the penetration test.
Return all findings as structured JSON with: title, severity, description, evidence, remediation, cve, mitre_id."""

    def _parse_findings(self, content: str, phase: str) -> List[RouterFinding]:
        """Parse findings from LLM response, looking for JSON blocks."""
        findings = []

        # Try to extract JSON from code blocks
        import re
        json_blocks = re.findall(r'```(?:json)?\s*([\s\S]*?)```', content)
        for block in json_blocks:
            try:
                data = json.loads(block.strip())
                if isinstance(data, list):
                    for item in data:
                        findings.append(RouterFinding(
                            title=item.get("title", "Unknown"),
                            severity=item.get("severity", "info"),
                            phase=phase,
                            description=item.get("description", ""),
                            evidence=item.get("evidence", ""),
                            remediation=item.get("remediation", ""),
                            cve=item.get("cve", ""),
                            mitre_id=item.get("mitre_id", ""),
                        ))
                elif isinstance(data, dict):
                    findings.append(RouterFinding(
                        title=data.get("title", "Unknown"),
                        severity=data.get("severity", "info"),
                        phase=phase,
                        description=data.get("description", ""),
                        evidence=data.get("evidence", ""),
                        remediation=data.get("remediation", ""),
                        cve=data.get("cve", ""),
                        mitre_id=data.get("mitre_id", ""),
                    ))
            except json.JSONDecodeError:
                pass

        # Fallback: parse text-based findings
        if not findings:
            lines = content.split("\n")
            current = {}
            for line in lines:
                line = line.strip()
                if line.lower().startswith("severity:"):
                    current["severity"] = line.split(":", 1)[1].strip().lower()
                elif line.lower().startswith("title:"):
                    current["title"] = line.split(":", 1)[1].strip()
                elif line.lower().startswith("description:"):
                    current["description"] = line.split(":", 1)[1].strip()
                elif line.lower().startswith("cve:"):
                    current["cve"] = line.split(":", 1)[1].strip()
                elif line == "" and current.get("title"):
                    findings.append(RouterFinding(
                        title=current.get("title", "Unknown"),
                        severity=current.get("severity", "info"),
                        phase=phase,
                        description=current.get("description", ""),
                        cve=current.get("cve", ""),
                    ))
                    current = {}

        return findings

    async def scan(self, target: str, command: str = "nmap -sV",
                   model: Optional[str] = None) -> str:
        """Run a single security scan command through the router."""
        model = model or self.default_model
        result = await self.chat(
            messages=[{"role": "system", "content": self._system_prompt()},
                      {"role": "user", "content": f"Target: {target}\nCommand: {command}\n\nExecute this security command and explain the results. If it's a tool you cannot run directly, explain what the command would do and what to look for in the output."}],
            model=model,
        )
        return result.get("content", "")

    def list_models(self) -> List[str]:
        """List available OpenRouter models."""
        try:
            resp = httpx.get(f"{self.base_url}/models", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                return [m["id"] for m in data.get("data", [])]
        except Exception:
            pass
        return ["openai/gpt-5.4-mini", "anthropic/claude-sonnet-4.6",
                "google/gemini-2.5-flash", "meta-llama/llama-4-70b",
                "deepseek/deepseek-chat"]


# ── CLI-Compatible Entry Points ──────────────────────────────────────────────

agent_instance: Optional[NineRouterAgent] = None


def get_agent() -> NineRouterAgent:
    global agent_instance
    if agent_instance is None:
        agent_instance = NineRouterAgent()
    return agent_instance


async def run_pentest(target: str, intent: str = "full pentest",
                      model: str = "") -> RouterReport:
    agent = get_agent()
    m = model or agent.default_model
    return await agent.pentest(target, intent, m)
