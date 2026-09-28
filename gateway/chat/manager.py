"""Chat Manager — session handling, intent routing, execution orchestration.

Supports:
- Multi-session conversations with persistence
- Natural language intent detection → subsystem routing
- Streaming responses via async generators
- Subsystem execution: pipeline, cron, cyber, reverse-engineering, router, research, doctor
- Code/shell execution in sandbox
- Tool output formatting (JSON, tables, syntax highlighting)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Tuple, Union

from engine.bounty import execute_bounty, get_bounty_board
from engine.publisher import AppPublisher, get_publisher

logger = logging.getLogger("pravidhi.chat")


# ── Types ─────────────────────────────────────────────────────────────────────

class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class IntentType(str, Enum):
    PIPELINE = "pipeline"
    CRON = "cron"
    CYBER = "cyber"
    RE = "reverse_engineering"
    ROUTER = "router"
    RESEARCH = "research"
    DOCTOR = "doctor"
    PROVIDER = "provider"
    SKILLS = "skills"
    BOUNTY = "bounty"
    PUBLISH = "publish"
    HELP = "help"
    ULTRAWORKER = "ultraworker"
    CHAT = "chat"
    EXECUTE = "execute"
    CODE = "code"
    SHELL = "shell"
    FILE = "file"
    STATUS = "status"
    UNKNOWN = "unknown"


@dataclass
class Message:
    role: MessageRole
    content: str
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])


@dataclass
class ChatSession:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    messages: List[Message] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    settings: Dict[str, Any] = field(default_factory=lambda: {
        "model": os.getenv("ROUTER_MODEL", "openai/gpt-5.4-mini"),
        "temperature": 0.3,
        "max_tokens": 1_000_000,
        "stream": True,
        "system_prompt": "You are Pravidhi Chat — an expert AI ecosystem controller. You can execute pipelines, manage cron jobs, run pentests, analyze binaries, and perform research. Explain your actions clearly.",
    })


# ── Intent Classifier ─────────────────────────────────────────────────────────

INTENT_PATTERNS: Dict[IntentType, List[str]] = {
    IntentType.PIPELINE: [
        r"\b(run|execute|process|pipeline)\s+.*(prompt|request|input)",
        r"\b(ask|question|think|reason)\s+.*\?$",
    ],
    IntentType.CRON: [
        r"\b(cron|schedule|job|timer|every|daily|hourly|weekly|monthly)\b",
        r"\b(schedule|auto|background|daemon)\b.*\b(job|task|run)\b",
    ],
    IntentType.CYBER: [
        r"\b(pentest|scan|cyber|security|hack|exploit|vulnerab|nmap|sqlmap|burp)\b",
        r"\b(mitre|attack|cve|owasp|recon|discovery)\b",
        r"\b(cyber)\s+(pentest|scan|skills|mitre|agents)\b",
    ],
    IntentType.RE: [
        r"\b(reverse|binary|analyze|decompile|ghidra|z3|symbolic)\b",
        r"\b(pe|elf|macho|firmware|malware|virus|malicious)\b",
        r"\b(re)\s+(analyze|symbols|overflow|decompile)\b",
    ],
    IntentType.ROUTER: [
        r"\b(router|9router|openrouter|model)\b",
        r"\b(router)\s+(pentest|scan|models)\b",
    ],
    IntentType.RESEARCH: [
        r"\b(research|train|learn|improve|converge|epoch|practice|cycle)\b",
        r"\b(auto.?research|training.?loop|skill.?gen)\b",
    ],
    IntentType.DOCTOR: [
        r"\b(doctor|diagnos|health|check|fix|repair|status)\b",
        r"\b(doctor)\s*(--fix|-f|--deps|--full)?\b",
        r"^pravidhi\s+doctor",
    ],
    IntentType.PROVIDER: [
        r"\b(provider|model|api.?key|credential|routing|endpoint)\b",
        r"\b(providers)\s+(list|config)\b",
    ],
    IntentType.SKILLS: [
        r"\b(skill|tool|capability|plugin|mcp)\b",
        r"\b(skills)\s+(list|search|discover)\b",
    ],
    IntentType.EXECUTE: [
        r"\b(run|exec|execute|deploy|start|launch)\s+(a |the |my )?(\w|-)+\b",
    ],
    IntentType.CODE: [
        r"```\w*$",
        r"\b(write|create|generate|make|build|implement)\s+(a |the |an )?(python|js|ts|rust|go|bash|script|code)\b",
        r"\b(code|script|program)\s+(to|that|for)\b",
    ],
    IntentType.SHELL: [
        r"^[\$#>]\s+",
        r"\b(shell|terminal|bash|zsh|command|run)\s+(command|script)\b",
    ],
    IntentType.FILE: [
        r"\b(file|read|write|edit|cat|ls|find|grep|open|save|delete|mv|cp)\b.*\b(path|file|dir|folder)\b",
        r"\b(read|show|view|open|list)\s+(file|directory|folder)\b",
    ],
    IntentType.STATUS: [
        r"^(status|stats|uptime|info|health)$",
        r"\b(show|get|what.?is)\s+(status|stats|health|state)\b",
        r"\b(system|service)\s+(status|info)\b",
    ],
    IntentType.BOUNTY: [
        r"\b(bounty|bounties|vibe|reward|earn|contribute|fund)\b",
        r"\b(post|create|claim|complete)\s+(bounty|bounty)\b",
        r"\b(bounty)\s+(list|create|claim|complete|stats|hunter)\b",
    ],
    IntentType.PUBLISH: [
        r"\b(publish|deploy|host|release|ship|launch)\s+(app|web|site|chat|ui)\b",
        r"\b(publish|deploy)\s+(this|chat|current|pravidhi)\b",
        r"\b(deploy)\s+(to|on)\s+(anyclaw|web|production)\b",
    ],
    IntentType.HELP: [
        r"^(help|\?|commands|what can you do)$",
        r"\b(help|guide|manual|doc|tutorial)\b",
    ],
    IntentType.ULTRAWORKER: [
        r"\b(ultra|parallel|ensemble|fusion|multi.?model|all.?models|consensus)\b",
        r"\b(ultraworker|ultra.?pool|parallel.?exec|distributed)\b",
        r"\b(run\s+on\s+all|use\s+all\s+models|compare\s+models)\b",
    ],
}


def classify_intent(text: str) -> Tuple[IntentType, float]:
    """Classify user message intent with confidence score."""
    text_lower = text.lower().strip()

    for intent, patterns in INTENT_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return intent, 0.85
    return IntentType.CHAT, 0.5


# ── Subsystem Executors ──────────────────────────────────────────────────────

async def execute_pipeline(text: str, **kwargs) -> Dict[str, Any]:
    """Run a prompt through the Pravidhi pipeline."""
    from engine.pipeline import Pipeline
    pipeline = Pipeline()
    ctx = await pipeline.run(text)
    return {
        "type": "pipeline",
        "request_id": ctx.request_id,
        "duration_ms": ctx.metadata.get("total_duration_ms", 0),
        "validation_score": ctx.validation_score,
        "errors": ctx.errors[:5],
        "output": str(ctx.final_output)[:3000] if ctx.final_output else "No output generated",
        "stages_completed": 7 - len(ctx.errors),
    }


async def execute_cron(action: str, **params) -> Dict[str, Any]:
    """Manage cron jobs."""
    from cron.scheduler import CronDB, CronJob, JobMode, parse_cron_expression
    db_path = os.path.expanduser("~/.pravidhi/cron.db")
    db = CronDB(db_path)

    if action in ("list", "ls", "show"):
        jobs = db.list_jobs(include_paused=True)
        return {
            "type": "cron_list",
            "jobs": [{
                "id": j.id[:8], "name": j.name, "schedule": j.schedule,
                "mode": j.mode.value if hasattr(j.mode, 'value') else str(j.mode),
                "paused": j.paused, "run_count": j.run_count,
                "success_count": j.success_count, "fail_count": j.fail_count,
                "last_run": datetime.fromtimestamp(j.last_run).isoformat() if j.last_run else None,
                "next_run": datetime.fromtimestamp(j.next_run).isoformat() if j.next_run else None,
            } for j in jobs],
            "total": len(jobs),
        }
    elif action in ("add", "create", "new"):
        name = params.get("name", "unnamed")
        schedule = params.get("schedule", "0 * * * *")
        command = params.get("command", "")
        prompt_text = params.get("prompt", "")
        parsed = parse_cron_expression(schedule)
        next_run = time.time() + 60
        if parsed and parsed["type"] == "interval":
            next_run = time.time() + parsed["seconds"]
        job = CronJob(
            name=name, schedule=schedule,
            mode=JobMode.NO_AGENT if command else JobMode.AGENT,
            command=command, prompt=prompt_text,
            next_run=next_run,
        )
        job_id = db.add_job(job)
        return {"type": "cron_add", "id": job_id[:8], "name": name, "schedule": schedule}
    elif action in ("pause", "stop"):
        job_id = params.get("id", params.get("name", ""))
        db.pause_job(job_id, True)
        return {"type": "cron_pause", "id": job_id}
    elif action in ("resume", "start"):
        job_id = params.get("id", params.get("name", ""))
        db.pause_job(job_id, False)
        return {"type": "cron_resume", "id": job_id}
    elif action in ("delete", "remove", "rm"):
        job_id = params.get("id", params.get("name", ""))
        db.delete_job(job_id)
        return {"type": "cron_delete", "id": job_id}
    return {"type": "cron_help", "message": "Usage: cron [list|add|pause|resume|delete]"}


async def execute_cyber(target: str = "", action: str = "pentest",
                         **params) -> Dict[str, Any]:
    """Run cybersecurity operations."""
    from router_agent.core import NineRouterAgent
    agent = NineRouterAgent()

    if action == "pentest":
        report = await agent.pentest(target, params.get("intent", "full pentest"))
        return {
            "type": "pentest",
            "target": target,
            "status": report.status,
            "duration": report.duration,
            "findings_count": len(report.findings),
            "findings": [{
                "title": f.title, "severity": f.severity,
                "phase": f.phase, "description": f.description[:200],
            } for f in report.findings[:10]],
        }
    elif action == "scan":
        command = params.get("command", "nmap -sV")
        result = await agent.scan(target, command)
        return {"type": "scan", "target": target, "result": result[:2000]}
    elif action == "skills":
        query = params.get("query", "")
        skills = list(agent.skills_index.values())
        if query:
            skills = [s for s in skills if query.lower() in s.get("name", "").lower()]
        return {"type": "skills", "total": len(skills), "skills": skills[:15]}
    return {"type": "cyber_help", "message": "Usage: cyber [pentest|scan|skills]"}


async def execute_re(path: str = "", action: str = "analyze",
                      **params) -> Dict[str, Any]:
    """Run reverse engineering operations."""
    from engine.reverse_engineering import BinaryAnalyzer, SymbolicExecutor
    import os as _os

    if action == "analyze":
        if not _os.path.exists(path):
            return {"type": "error", "message": f"File not found: {path}"}
        analyzer = BinaryAnalyzer()
        report = await analyzer.analyze(path, params.get("depth", "basic"))
        return {
            "type": "binary_analysis",
            "path": path,
            "format": report.binary.format.value,
            "arch": report.binary.arch,
            "size": report.binary.size,
            "entropy": report.binary.entropy,
            "strings": len(report.binary.strings),
            "hashes": report.binary.hashes,
            "vulnerabilities": len(report.vulnerabilities),
            "summary": report.summary,
        }
    elif action in ("overflow", "buffer"):
        executor = SymbolicExecutor()
        result = executor.analyze_buffer_overflow(
            params.get("buffer_size", 100),
            params.get("offset", 50),
            params.get("access_size", 4),
        )
        return {"type": "overflow_check", **result}
    return {"type": "re_help", "message": "Usage: re [analyze|overflow]"}


async def execute_research(action: str = "status", **params) -> Dict[str, Any]:
    """Run research operations."""
    from research.training_loop import TrainingLoop

    if action in ("cycle", "run", "start"):
        result = await TrainingLoop().run_analysis()
        return {"type": "research_cycle", **result}
    elif action in ("practice", "train"):
        prompt = params.get("prompt", "Improve your understanding")
        epochs = params.get("epochs", 3)
        results = await TrainingLoop().practice_loop(prompt, epochs)
        return {"type": "practice", "epochs": len(results), "results": results}
    else:
        status = TrainingLoop().get_status()
        return {"type": "research_status", **status}


async def execute_ultraworker(action: str = "status", **params) -> Dict[str, Any]:
    """Run ultraworker operations."""
    from engine.ultraworker import UltraWorkerPool, get_pool, start_pool, WorkItem, WorkItemType

    if action in ("start", "run", "init", "launch"):
        n = params.get("num_workers", 3)
        pool = await start_pool(n)
        return {"type": "ultra_status", "pool_started": True, "workers": n, "pool_status": pool.get_status()}

    elif action in ("stop", "shutdown"):
        await get_pool().stop()
        return {"type": "ultra_status", "pool_stopped": True}

    elif action in ("pipeline", "run_pipeline"):
        prompt = params.get("prompt", "")
        parallel = params.get("parallel", 3)
        pool = get_pool()
        if not pool._running:
            await pool.start(parallel)
        result = await pool.run_parallel_pipeline(prompt, parallel)
        return result

    elif action in ("chat", "ask"):
        messages = params.get("messages", [{"role": "user", "content": params.get("prompt", "")}])
        parallel = params.get("parallel", 3)
        pool = get_pool()
        if not pool._running:
            await pool.start(parallel)
        item = WorkItem(type=WorkItemType.LLM_CHAT, payload={"messages": messages})
        fused = await pool.run_parallel(item, parallel)
        return {
            "type": "ultra_chat",
            "strategy": fused.strategy.value,
            "consensus_score": fused.consensus_score,
            "workers_used": fused.workers_used,
            "total_latency_ms": round(fused.total_latency_ms, 1),
            "content": fused.content[:3000],
            "primary_model": fused.primary.model if fused.primary else None,
        }

    # Default: status
    return {"type": "ultra_status", "status": get_pool().get_status()}


async def execute_doctor(action: str = "check", **params) -> Dict[str, Any]:
    """Run doctor diagnostics."""
    from gateway.doctor import DoctorEngine

    engine = DoctorEngine()
    if action in ("fix", "--fix"):
        results = engine.diagnose()
        fixes = engine.auto_fix(results)
        return {
            "type": "doctor_fix",
            "fixes": [{"check": f["check"], "status": f["status"],
                        "message": f["message"]} for f in fixes],
        }
    else:
        results = engine.diagnose()
        summary = engine.summary(results)
        return {
            "type": "doctor",
            "results": [{
                "name": r.name, "passed": r.passed,
                "severity": r.severity, "message": r.message,
            } for r in results],
            "summary": summary,
        }


async def execute_shell(command: str) -> Dict[str, Any]:
    """Execute a shell command in sandbox."""
    from engine.sandbox import CodeSandbox
    sandbox = CodeSandbox()
    result = await sandbox.execute_shell(command)
    return {
        "type": "shell",
        "command": command,
        "stdout": result.stdout[:5000],
        "stderr": result.stderr[:1000],
        "return_code": result.return_code,
    }


async def execute_code(code: str, language: str = "python") -> Dict[str, Any]:
    """Execute code in sandbox."""
    from engine.sandbox import CodeSandbox
    sandbox = CodeSandbox()
    if language == "python":
        result = await sandbox.execute_python(code)
    else:
        result = await sandbox.execute_shell(f"cat > /tmp/exec_code << 'EOF'\n{code}\nEOF\n")
    return {
        "type": "code_execution",
        "language": language,
        "stdout": result.stdout[:5000],
        "stderr": result.stderr[:1000],
        "return_code": result.return_code,
    }


# ── Intent Dispatcher ────────────────────────────────────────────────────────

INTENT_DISPATCH: Dict[IntentType, Callable] = {
    IntentType.PIPELINE: lambda text, **kw: execute_pipeline(text, **kw),
    IntentType.CRON: lambda text, **kw: execute_cron(kw.pop("action", "list"), **kw),
    IntentType.CYBER: lambda text, **kw: execute_cyber(target=kw.pop("target", text), action=kw.pop("action", "pentest"), **kw),
    IntentType.RE: lambda text, **kw: execute_re(path=kw.pop("path", ""), action=kw.pop("action", "analyze"), **kw),
    IntentType.ROUTER: lambda text, **kw: execute_cyber(target=kw.pop("target", text), action=kw.pop("action", "pentest"), **kw),
    IntentType.RESEARCH: lambda text, **kw: execute_research(action=kw.pop("action", "status"), **kw),
    IntentType.DOCTOR: lambda text, **kw: execute_doctor(action=kw.pop("action", "check"), **kw),
    IntentType.SHELL: lambda text, **kw: execute_shell(kw.pop("command", text)),
    IntentType.CODE: lambda text, **kw: execute_code(kw.pop("code", text), kw.pop("language", "python")),
    IntentType.STATUS: lambda text, **kw: get_system_status(),
    IntentType.PROVIDER: lambda text, **kw: get_providers(),
    IntentType.SKILLS: lambda text, **kw: get_skills(),
    IntentType.BOUNTY: lambda text, **kw: execute_bounty(action=kw.pop("action", "list"), **kw),
    IntentType.PUBLISH: lambda text, **kw: execute_publish(text=text, action=kw.pop("action", "status"), **kw),
    IntentType.HELP: lambda text, **kw: get_help(),
    IntentType.ULTRAWORKER: lambda text, **kw: execute_ultraworker(
        action=kw.pop("action", "status"),
        prompt=kw.pop("prompt", text),
        parallel=kw.pop("parallel", 3),
        **kw
    ),
    IntentType.FILE: lambda text, **kw: handle_file(text, **kw),
}


# ── Chat Manager ──────────────────────────────────────────────────────────────

class ChatManager:
    """Manages chat sessions, dispatching intents to subsystems."""

    def __init__(self):
        self.sessions: Dict[str, ChatSession] = {}
        self._session_dir = Path.home() / ".pravidhi" / "chat-sessions"
        self._session_dir.mkdir(parents=True, exist_ok=True)

    def create_session(self, settings: Optional[Dict[str, Any]] = None) -> ChatSession:
        session = ChatSession()
        if settings:
            session.settings.update(settings)
        session.messages.append(Message(
            role=MessageRole.SYSTEM,
            content="Pravidhi Chat initialized. All subsystems ready.",
        ))
        self.sessions[session.id] = session
        return session

    def get_session(self, session_id: str) -> Optional[ChatSession]:
        return self.sessions.get(session_id)

    def add_message(self, session_id: str, role: MessageRole, content: str,
                     metadata: Optional[Dict[str, Any]] = None) -> Optional[Message]:
        session = self.get_session(session_id)
        if not session:
            return None
        msg = Message(role=role, content=content, metadata=metadata or {})
        session.messages.append(msg)
        session.updated_at = time.time()
        return msg

    def get_history(self, session_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        session = self.get_session(session_id)
        if not session:
            return []
        return [{
            "role": m.role.value,
            "content": m.content[:500],
            "timestamp": m.timestamp,
            "id": m.id,
            "metadata": m.metadata,
        } for m in session.messages[-limit:]]

    async def process_message(self, session_id: str, text: str) -> AsyncGenerator[Dict[str, Any], None]:
        """Process a user message and yield response chunks."""
        session = self.get_session(session_id)
        if not session:
            yield {"type": "error", "content": "Session not found"}
            return

        # Detect intent
        intent, confidence = classify_intent(text)

        yield {
            "type": "intent",
            "intent": intent.value,
            "confidence": round(confidence, 2),
            "content": f"Detected: **{intent.value}** intent ({confidence:.0%} confidence)",
        }

        await asyncio.sleep(0.1)

        # Add user message
        self.add_message(session_id, MessageRole.USER, text)

        # Dispatch to appropriate subsystem
        if intent in INTENT_DISPATCH:
            dispatcher = INTENT_DISPATCH[intent]
            try:
                # Extract parameters from text
                params = extract_params(text, intent)
                result = await dispatcher(text, **params)

                yield {"type": "result", "data": result, "content": format_result(result)}

                # Add assistant response
                self.add_message(
                    session_id, MessageRole.ASSISTANT,
                    format_result(result),
                    metadata={"result_type": result.get("type", "unknown"), "raw": True},
                )
            except Exception as e:
                logger.error(f"Execution error: {e}")
                error_msg = f"**Error**: {str(e)}"
                yield {"type": "error", "content": error_msg}
                self.add_message(session_id, MessageRole.ASSISTANT, error_msg)

        # LLM fallback for chat/unknown
        if intent in (IntentType.CHAT, IntentType.UNKNOWN):
            yield {
                "type": "reasoning",
                "content": f"I'll handle this as a general chat. Let me think about: {text[:100]}...",
            }
            await asyncio.sleep(0.3)
            # Try LLM via router agent
            try:
                from router_agent.core import NineRouterAgent
                agent = NineRouterAgent()
                response = await agent.chat(
                    messages=[
                        {"role": "system", "content": session.settings.get("system_prompt",
                            "You are Pravidhi Chat, an AI ecosystem controller.")},
                        {"role": "user", "content": text},
                    ],
                    model=session.settings.get("model", "openai/gpt-5.4-mini"),
                    temperature=session.settings.get("temperature", 0.3),
                )
                content = response.get("content", "I'm not sure how to respond.")
                yield {"type": "chat", "content": content}
                self.add_message(session_id, MessageRole.ASSISTANT, content)
            except Exception as e:
                fallback = "I can help you with: pipeline execution, cron management, cybersecurity pentesting, reverse engineering, research cycles, doctor diagnostics, code execution, and file operations. Try asking about any of these!"
                yield {"type": "chat", "content": fallback}
                self.add_message(session_id, MessageRole.ASSISTANT, fallback)

        yield {"type": "done", "session_id": session_id}

    def delete_session(self, session_id: str) -> bool:
        if session_id in self.sessions:
            del self.sessions[session_id]
            return True
        return False

    def list_sessions(self) -> List[Dict[str, Any]]:
        return [{
            "id": s.id,
            "created_at": s.created_at,
            "updated_at": s.updated_at,
            "message_count": len(s.messages),
        } for s in sorted(self.sessions.values(), key=lambda x: x.updated_at, reverse=True)]


# ── Parameter Extraction ─────────────────────────────────────────────────────

def extract_params(text: str, intent: IntentType) -> Dict[str, Any]:
    """Extract parameters from natural language for each intent type."""
    params: Dict[str, Any] = {}
    text_lower = text.lower()

    if intent == IntentType.CRON:
        # Extract action
        for action in ("list", "ls", "show", "add", "create", "pause", "stop", "resume", "start", "delete", "remove", "rm"):
            if action in text_lower.split():
                params["action"] = action
                break
        if "action" not in params:
            params["action"] = "list"
        # Extract schedule
        sched_match = re.search(r"(every|each)\s+(\d+)\s*(hour|minute|day|month)", text_lower)
        if sched_match:
            params["schedule"] = f"*/{sched_match.group(2)} {_cron_unit(sched_match.group(3))} * * *"
        # Extract name
        name_match = re.search(r"(?:name|called|named)\s+['\"]?(\w+)['\"]?", text_lower)
        if name_match:
            params["name"] = name_match.group(1)
        # Extract id
        id_match = re.search(r"(?:id|job)\s+['\"]?(\w+)['\"]?", text_lower)
        if id_match:
            params["id"] = id_match.group(1)
        # Extract command
        cmd_match = re.search(r"(?:run|command|exec)\s+['\"]?(.+?)['\"]?(?:\s+as|\s+on|\s*$)", text_lower)
        if cmd_match:
            params["command"] = cmd_match.group(1)

    elif intent in (IntentType.CYBER, IntentType.ROUTER):
        # Extract target (URL, IP, domain)
        target_match = re.search(r"(?:target|against|on|scan)\s+['\"]?([a-zA-Z0-9.-]+\.[a-zA-Z]{2,}|(?:\d{1,3}\.){3}\d{1,3})['\"]?", text_lower)
        if target_match:
            params["target"] = target_match.group(1)
        else:
            # Try to find any URL-like pattern
            url_match = re.search(r'(https?://[^\s]+|[\w.-]+\.[a-zA-Z]{2,}(?:/[^\s]*)?)', text)
            if url_match:
                params["target"] = url_match.group(1)
        # Extract action
        for action in ("pentest", "scan", "skills", "mitre"):
            if action in text_lower:
                params["action"] = action
                break
        if "action" not in params:
            params["action"] = "pentest"
        # Extract intent for pentest
        for intent_val in ("recon", "discovery", "exploitation", "privesc"):
            if intent_val in text_lower:
                params["intent"] = intent_val
                break
        # Extract query for skills
        query_match = re.search(r"(?:search|find|about|for)\s+['\"]?(.+?)['\"]?(?:\s+skills|\s*$)", text_lower)
        if query_match:
            params["query"] = query_match.group(1)

    elif intent == IntentType.RE:
        # Extract path
        path_match = re.search(r"(?:file|binary|path|analyze)\s+['\"]?([/\.\w-]+)['\"]?", text)
        if path_match:
            params["path"] = path_match.group(1)
        # Extract action
        for action in ("analyze", "overflow", "buffer", "symbols"):
            if action in text_lower:
                params["action"] = action
                break

    elif intent == IntentType.RESEARCH:
        for action in ("cycle", "run", "start", "practice", "train", "status"):
            if action in text_lower:
                params["action"] = action
                break

    elif intent == IntentType.DOCTOR:
        if "--fix" in text or "fix" in text_lower.split():
            params["action"] = "fix"
        elif "--deps" in text or "deps" in text_lower or "dependencies" in text_lower:
            params["action"] = "deps"

    elif intent == IntentType.SHELL:
        # Extract command after shell/bash/run
        cmd_match = re.search(r"(?:run|execute|shell|bash|command)\s+['\"]?(.+?)['\"]?$", text)
        if cmd_match:
            params["command"] = cmd_match.group(1)
        else:
            params["command"] = text

    elif intent == IntentType.CODE:
        # Extract code block if present
        code_match = re.search(r'```(\w*)\n(.+?)```', text, re.DOTALL)
        if code_match:
            params["language"] = code_match.group(1) or "python"
            params["code"] = code_match.group(2)

    return params


def _cron_unit(unit: str) -> str:
    return {"hour": "0", "minute": "*", "day": "*", "month": "*"}.get(unit, "*")


# ── Response Formatters ──────────────────────────────────────────────────────

def format_result(result: Dict[str, Any]) -> str:
    """Format a result dict into a human-readable markdown string."""
    rtype = result.get("type", "unknown")

    if rtype == "pipeline":
        score = result.get("validation_score", 0)
        score_bar = "🟢" if score >= 0.8 else "🟡" if score >= 0.5 else "🔴"
        return (
            f"**Pipeline Complete** {score_bar}\n"
            f"- Duration: `{result.get('duration_ms', 0):.0f}ms`\n"
            f"- Validation: `{score:.0%}`\n"
            f"- Stages completed: `{result.get('stages_completed', 0)}/7`\n"
            f"- Output: _{result.get('output', '')[:300]}_"
        )

    if rtype == "cron_list":
        jobs = result.get("jobs", [])
        if not jobs:
            return "**No cron jobs configured.** Use `cron add` to create one."
        lines = ["**Cron Jobs**"]
        for j in jobs:
            status = "⏸" if j.get("paused") else "▶"
            lines.append(f"- `{j['id']}` {status} **{j['name']}** `{j['schedule']}` ({j['mode']}) "
                         f"runs:{j['run_count']} success:{j['success_count']} fail:{j['fail_count']}")
        return "\n".join(lines)

    if rtype == "cron_add":
        return f"**Cron Job Created** ✅\n- Name: `{result.get('name')}`\n- ID: `{result.get('id')}`\n- Schedule: `{result.get('schedule')}`"

    if rtype in ("pentest", "scan"):
        lines = [f"**Pentest Results** — {result.get('target', '')}"]
        if result.get("status"):
            lines.append(f"- Status: `{result['status']}` | Duration: `{result.get('duration', 0):.1f}s`")
        if result.get("findings"):
            lines.append(f"- **{result.get('findings_count', 0)} findings:**")
            for f in result["findings"][:5]:
                severity_colors = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵", "info": "⚪"}
                icon = severity_colors.get(f.get("severity", "info"), "⚪")
                lines.append(f"  {icon} **{f['severity'].upper()}** {f['title'][:80]}")
        return "\n".join(lines)

    if rtype == "binary_analysis":
        return (
            f"**Binary Analysis** — `{result.get('path', '')}`\n"
            f"- Format: `{result.get('format', '?')}` | Arch: `{result.get('arch', '?')}`\n"
            f"- Size: `{result.get('size', 0):,} bytes` | Entropy: `{result.get('entropy', 0):.2f}`\n"
            f"- Strings: `{result.get('strings', 0)}` | Vulnerabilities: `{result.get('vulnerabilities', 0)}`\n"
            f"- Summary: _{result.get('summary', '')}_"
        )

    if rtype == "research_cycle":
        return (
            f"**Research Cycle**\n"
            f"- Epoch: `{result.get('epoch')}`\n"
            f"- Accuracy: `{result.get('accuracy', 0):.1%}`\n"
            f"- Loss: `{result.get('loss', 0):.3f}`\n"
            f"- Skills generated: `{len(result.get('skills_generated', []))}`\n"
            f"- Converged: `{result.get('converged', False)}`"
        )

    if rtype == "doctor":
        summary = result.get("summary", {})
        passed = summary.get("passed", 0)
        errors = summary.get("errors", 0)
        return f"**Doctor Diagnostics** {'✅' if errors == 0 else '❌'}\n- Passed: `{passed}` | Errors: `{errors}`"

    if rtype == "doctor_fix":
        fixes = result.get("fixes", [])
        fixed = sum(1 for f in fixes if f.get("status") == "fixed")
        return f"**Auto-Fix Complete** 🔧\n- Fixed: `{fixed}/{len(fixes)}` issues"

    if rtype == "shell":
        cmd = result.get("command", "")
        stdout = result.get("stdout", "")
        stderr = result.get("stderr", "")
        rc = result.get("return_code", -1)
        out = f"**Shell** `$ {cmd}`\n- Exit code: `{rc}`"
        if stdout:
            out += f"\n```\n{stdout[:1000]}\n```"
        if stderr:
            out += f"\n```stderr\n{stderr[:500]}\n```"
        return out

    if rtype == "code_execution":
        return (
            f"**Code Execution** ({result.get('language', 'python')})\n"
            f"- Return code: `{result.get('return_code')}`\n"
            f"```\n{result.get('stdout', '')[:1000]}\n```"
        )

    if rtype == "skills":
        skills = result.get("skills", [])
        return f"**Skills** — {result.get('total', 0)} available\n" + "\n".join(
            f"- `{s.get('id', s.get('name', '?'))}`" for s in skills[:10]
        )

    if rtype in ("ultra_status",):
        s = result.get("status", {})
        if isinstance(s, dict):
            stats = s.get("stats", {})
            workers = s.get("workers", {})
            return (
                f"**UltraWorker Pool** {'✅' if s.get('pool_size',0) > 0 else '⏸'}\n"
                f"- Workers: `{s.get('pool_size', 0)}`  "
                f"Queue: `{s.get('queue_size', 0)}`\n"
                f"- Completed: `{stats.get('completed', 0)}`  "
                f"Failed: `{stats.get('failed', 0)}`\n"
                f"- Fusion: `{s.get('fusion_strategy', 'best_of_n')}`  "
                f"Max parallel: `{s.get('max_parallel', 3)}`"
            )
        return f"**UltraWorker** {'Started' if result.get('pool_started') else 'Stopped' if result.get('pool_stopped') else 'Unknown'}"

    if rtype in ("ultra_pipeline", "ultra_chat"):
        return (
            f"**Ultra {'Pipeline' if 'pipeline' in rtype else 'Chat'}** 🌐\n"
            f"- Strategy: `{result.get('strategy', 'best_of_n')}`  "
            f"Consensus: `{result.get('consensus_score', 0):.1%}`\n"
            f"- Workers: `{result.get('workers_used', 0)}/{result.get('workers_total', 0)}`  "
            f"Latency: `{result.get('total_latency_ms', 0):.0f}ms`\n"
            f"- Primary model: `{result.get('primary_model', 'N/A')}`\n"
            f"- Result: _{result.get('content', '')[:500]}_"
        )

    if rtype in ("system_status",):
        return (
            f"**System Status**\n"
            f"- Service: `{result.get('service', 'pravidhi')}`\n"
            f"- Tools: `{result.get('tools', 0)}` | Skills: `{result.get('skills', 0)}`\n"
            f"- Providers: `{result.get('providers', 0)}` | Cron: `{'✅' if result.get('cron_running') else '⏸'}`"
        )

    if rtype == "error":
        return f"**Error** ❌\n{result.get('message', 'Unknown error')}"

    return f"```json\n{json.dumps(result, indent=2)[:500]}\n```"


# ── Publish Handler ──────────────────────────────────────────────────────────

async def execute_publish(text: str = "", action: str = "status", **params) -> Dict[str, Any]:
    """Publish Pravidhi apps to Anyclaw hosting."""
    from engine.publisher import AppPublisher

    publisher = AppPublisher()
    
    if action in ("deploy", "publish", "chat"):
        title = params.get("title", "Pravidhi Neural Chat")
        description = params.get("description", "Advanced AI ecosystem controller with pipeline execution, pentesting, reverse engineering, research, and more.")
        app_id = params.get("app_id", "pravidhi-chat")
        
        result = await AppPublisher.publish_chat_ui(
            title=title, description=description, app_id=app_id,
        )
        if result.success:
            return {
                "type": "publish_success",
                "app_id": result.app_id,
                "claim_url": result.claim_url,
                "message": f"App deployed! Claim it at: {result.claim_url}",
            }
        else:
            return {
                "type": "publish_error",
                "message": f"Deploy failed: {result.error}",
            }
    
    elif action in ("list", "apps", "ls"):
        apps = await publisher.list_apps()
        return {
            "type": "publish_list",
            "apps": apps[:20],
            "total": len(apps),
        }
    
    return {
        "type": "publish_help",
        "message": "Usage: publish [deploy|list]. Try 'publish deploy' to deploy the Pravidhi Chat SPA."
    }


# ── Utility Handlers ─────────────────────────────────────────────────────────

async def get_system_status() -> Dict[str, Any]:
    from engine.registry import get_registry
    registry = get_registry()
    stats = {
        "service": "pravidhi",
        "tools": len(registry.list_tools()),
        "skills": len(registry.skills),
        "providers": len(registry.list_providers()),
        "cron_running": False,
    }
    return {"type": "system_status", **stats}


async def get_providers() -> Dict[str, Any]:
    from engine.provider_router import BUILTIN_PROVIDERS
    providers = []
    for name, info in BUILTIN_PROVIDERS.items():
        key = os.getenv(info.get("env_key", ""), "")
        providers.append({
            "name": name,
            "configured": bool(key),
            "models": list(info.get("models", {}).keys()),
        })
    return {"type": "providers", "providers": providers}


async def get_skills() -> Dict[str, Any]:
    from engine.registry import get_registry
    registry = get_registry()
    skills = [{"name": k, "description": v.description[:100]} for k, v in registry.skills.items()]
    return {"type": "skills", "total": len(skills), "skills": skills}


async def get_help() -> Dict[str, Any]:
    return {"type": "help", "content": """**Pravidhi Chat — Available Commands**

**Pipeline** — `run <prompt>`, ask questions, think through problems
**Cron** — `cron list`, `cron add`, `cron pause`, `cron resume`, `cron delete`
**Cyber** — `pentest example.com`, `scan example.com --command nmap -sV`, `skills sql injection`
**Reverse Engineering** — `analyze /bin/ls`, `check buffer overflow size=100 offset=95`
**Router** — `router pentest example.com`, `router models`
**Research** — `research cycle`, `research status`, `practice <prompt>`
**Doctor** — `doctor`, `doctor --fix`, `check health`
**Shell** — `run <command>`, `` `ls -la` ``
**Code** — write Python/JS/TS/Rust/Bash code in markdown blocks
**System** — `status`, `stats`, `help`, `providers`, `skills`
"""}


async def handle_file(text: str, **kw) -> Dict[str, Any]:
    """Handle file operations."""
    text_lower = text.lower()
    if "read" in text_lower or "show" in text_lower or "cat" in text_lower:
        file_match = re.search(r"(?:read|show|cat|view|open)\s+(.+?)(?:\s|$)", text)
        if file_match:
            path = os.path.expanduser(file_match.group(1).strip().strip("'\"`"))
            try:
                content = Path(path).read_text()
                return {"type": "file_content", "path": path, "content": content[:3000]}
            except Exception as e:
                return {"type": "error", "message": f"Cannot read {path}: {e}"}
    if "list" in text_lower or "ls" in text_lower.split():
        dir_match = re.search(r"(?:list|ls)\s+(.+?)(?:\s|$)", text)
        path = os.path.expanduser(dir_match.group(1) if dir_match else ".")
        try:
            files = list(Path(path).iterdir())
            return {"type": "file_list", "path": path, "files": [str(f.name) for f in files[:50]]}
        except Exception as e:
            return {"type": "error", "message": str(e)}
    return {"type": "error", "message": "File operation not recognized. Try: read, list, ls"}
