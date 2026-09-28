"""Execution trace engine — real-time visibility into pipeline stages, tool calls, model selection.

Generates structured traces for each execution:
- Pipeline stage progress (7 stages with timing)
- Tool calls (which tool, input, output)
- Model selection decisions (why this model, fallbacks)
- Resource usage (tokens, time, retries)

These traces are streamed to the frontend for live visualization.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional, AsyncGenerator

logger = logging.getLogger("pravidhi.trace")


class TraceEventType(str, Enum):
    PIPELINE_STAGE = "pipeline_stage"
    MODEL_SELECTION = "model_selection"
    MODEL_ROTATION = "model_rotation"
    TOOL_CALL = "tool_call"
    LLM_REQUEST = "llm_request"
    LLM_RESPONSE = "llm_response"
    VALIDATION = "validation"
    ERROR = "error"
    SUBSYSTEM_EXEC = "subsystem_exec"
    RESOURCE_METRIC = "resource_metric"
    SYSTEM_INFO = "system_info"


@dataclass
class TraceEvent:
    """A single trace event with timing and metadata."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    type: TraceEventType = TraceEventType.SYSTEM_INFO
    title: str = ""
    description: str = ""
    status: str = "running"  # running | success | error | warning
    started_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    duration_ms: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    children: List[str] = field(default_factory=list)  # child event IDs

    def complete(self, status: str = "success", **extra):
        self.completed_at = time.time()
        self.duration_ms = (self.completed_at - self.started_at) * 1000
        self.status = status
        self.metadata.update(extra)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["type"] = self.type.value
        d["status"] = self.status
        return d

    @classmethod
    def pipeline_stage(cls, stage_name: str, stage_num: int, total: int = 7) -> "TraceEvent":
        return cls(
            type=TraceEventType.PIPELINE_STAGE,
            title=f"Stage {stage_num}/{total}: {stage_name}",
            description=f"Executing pipeline stage {stage_name}",
            metadata={"stage": stage_name, "stage_num": stage_num, "total": total},
        )

    @classmethod
    def model_selection(cls, model_id: str, reason: str = "preferred") -> "TraceEvent":
        return cls(
            type=TraceEventType.MODEL_SELECTION,
            title=f"Model: {model_id}",
            description=f"Selected via {reason}",
            metadata={"model": model_id, "reason": reason},
        )

    @classmethod
    def tool_call(cls, tool_name: str, input_summary: str = "") -> "TraceEvent":
        return cls(
            type=TraceEventType.TOOL_CALL,
            title=f"Tool: {tool_name}",
            description=input_summary,
            metadata={"tool": tool_name},
        )

    @classmethod
    def error(cls, message: str, source: str = "") -> "TraceEvent":
        return cls(
            type=TraceEventType.ERROR,
            title=f"Error in {source}" if source else "Error",
            description=message,
            status="error",
            metadata={"source": source},
        )


class TraceSession:
    """A single execution trace session — captures all events for one user request."""

    def __init__(self, request_id: str = ""):
        self.request_id = request_id or uuid.uuid4().hex[:12]
        self.session_start = time.time()
        self.events: List[TraceEvent] = []
        self._event_stack: List[str] = []  # parent ID stack
        self._completed = False

    @property
    def duration_ms(self) -> float:
        return (time.time() - self.session_start) * 1000

    def add_event(self, event: TraceEvent) -> TraceEvent:
        """Add an event and return it (so caller can complete it later)."""
        # Set parent if we have a stack
        if self._event_stack:
            parent_id = self._event_stack[-1]
            event.metadata["parent_id"] = parent_id
            # Add to parent's children
            for e in self.events:
                if e.id == parent_id:
                    e.children.append(event.id)
                    break
        self.events.append(event)
        return event

    def push_event(self, event: TraceEvent) -> TraceEvent:
        """Add event and set as current parent for subsequent events."""
        self.add_event(event)
        self._event_stack.append(event.id)
        return event

    def pop_event(self) -> Optional[str]:
        """Pop the current parent from the stack."""
        if self._event_stack:
            return self._event_stack.pop()
        return None

    def complete(self, status: str = "success"):
        self._completed = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "duration_ms": self.duration_ms,
            "events": [e.to_dict() for e in self.events],
            "completed": self._completed,
        }

    async def stream_events(self) -> AsyncGenerator[Dict[str, Any], None]:
        """Yield events as they happen for streaming to frontend."""
        # Send the trace header
        yield {
            "type": "trace_start",
            "request_id": self.request_id,
            "timestamp": self.session_start,
        }

        sent_ids = set()
        while not self._completed or len(sent_ids) < len(self.events):
            for event in self.events:
                if event.id not in sent_ids:
                    sent_ids.add(event.id)
                    yield {
                        "type": "trace_event",
                        "event": event.to_dict(),
                    }
            if self._completed:
                break
            await asyncio.sleep(0.05)

        yield {
            "type": "trace_end",
            "request_id": self.request_id,
            "duration_ms": self.duration_ms,
            "total_events": len(self.events),
        }


class TraceManager:
    """Manages multiple trace sessions."""

    def __init__(self, max_sessions: int = 50):
        self.sessions: Dict[str, TraceSession] = {}
        self.max_sessions = max_sessions

    def create_session(self, request_id: Optional[str] = None) -> TraceSession:
        """Create a new trace session."""
        session = TraceSession(request_id)
        self.sessions[session.request_id] = session
        # Prune old sessions
        if len(self.sessions) > self.max_sessions:
            oldest = sorted(self.sessions.keys(), key=lambda k: self.sessions[k].session_start)
            for k in oldest[:len(self.sessions) - self.max_sessions]:
                del self.sessions[k]
        return session

    def get_session(self, request_id: str) -> Optional[TraceSession]:
        return self.sessions.get(request_id)

    def get_recent(self, limit: int = 10) -> List[Dict[str, Any]]:
        sessions = sorted(
            self.sessions.values(),
            key=lambda s: s.session_start,
            reverse=True,
        )[:limit]
        return [s.to_dict() for s in sessions]


# Global trace manager
_trace_manager: Optional[TraceManager] = None


def get_trace_manager() -> TraceManager:
    global _trace_manager
    if _trace_manager is None:
        _trace_manager = TraceManager()
    return _trace_manager
