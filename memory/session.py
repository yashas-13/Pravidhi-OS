"""Hierarchical memory system — session, working, and long-term memory.

Inspired by Hermes Agent's MEMORY.md / USER.md with additional
long-term vector storage for patterns and experiences.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from engine.config import get_config

logger = logging.getLogger("pravidhi.memory")


# ── Data Types ───────────────────────────────────────────────────────────────

@dataclass
class MemoryEntry:
    """A single memory entry."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    content: str = ""
    category: str = "general"  # env_fact | preference | convention | lesson | skill
    created_at: float = field(default_factory=time.time)
    access_count: int = 0
    tags: List[str] = field(default_factory=list)


@dataclass
class SessionContext:
    """Current session state."""
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    started_at: float = field(default_factory=time.time)
    user_inputs: List[str] = field(default_factory=list)
    assistant_outputs: List[str] = field(default_factory=list)
    tool_calls: List[Dict] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


# ── Working Memory (MEMORY.md / USER.md) ─────────────────────────────────────

class WorkingMemory:
    """Bounded working memory — persists across sessions.

    Two files:
    - memory.md: Agent's personal notes (environment facts, conventions)
    - user.md:  User profile (preferences, style, expectations)
    """

    def __init__(self):
        config = get_config().memory
        self.memory_path = Path(config.working.file.replace("~", str(Path.home())))
        self.user_path = Path(config.user_profile.file.replace("~", str(Path.home())))
        self.memory_max = config.working.max_chars
        self.user_max = config.user_profile.max_chars
        self._entries: List[MemoryEntry] = []
        self._load()

    def _load(self) -> None:
        """Load memory from disk."""
        if self.memory_path.exists():
            lines = self.memory_path.read_text().split("§")
            for line in lines:
                line = line.strip()
                if line:
                    self._entries.append(MemoryEntry(
                        content=line,
                        category=self._classify(line),
                    ))

    def _save(self) -> None:
        """Save entries back to disk, respecting char limits."""
        content = "\n§ ".join(e.content for e in self._entries)
        if len(content) > self.memory_max:
            # Trim oldest entries
            while len(content) > self.memory_max and self._entries:
                self._entries.pop(0)
                content = "\n§ ".join(e.content for e in self._entries)

        self.memory_path.parent.mkdir(parents=True, exist_ok=True)
        self.memory_path.write_text(content)

    def _classify(self, content: str) -> str:
        lower = content.lower()
        if "prefer" in lower or "like" in lower or "dislike" in lower:
            return "preference"
        if "project" in lower or "repo" in lower or "~/" in content or "/home" in content:
            return "env_fact"
        if "convention" in lower or "style" in lower or "pattern" in lower:
            return "convention"
        return "general"

    def add(self, content: str, category: str = "general") -> MemoryEntry:
        """Add a memory entry."""
        entry = MemoryEntry(content=content, category=category)
        self._entries.append(entry)
        self._save()
        return entry

    def remove(self, content_substring: str) -> bool:
        """Remove entries matching substring."""
        before = len(self._entries)
        self._entries = [e for e in self._entries if content_substring not in e.content]
        if len(self._entries) < before:
            self._save()
            return True
        return False

    def get_all(self) -> List[MemoryEntry]:
        return list(self._entries)

    def get_formatted(self, max_chars: Optional[int] = None) -> str:
        """Get formatted memory block for system prompt injection."""
        limit = max_chars or self.memory_max
        entries = self._entries
        content = "§ ".join(e.content for e in entries)
        usage = len(content)
        pct = min(usage / limit * 100, 100)

        header = f"MEMORY (pravidhi notes) [{pct:.0f}% — {usage:,}/{limit:,} chars]"
        return f"{header}\n{content[:limit]}"

    def usage_pct(self) -> float:
        content = "§ ".join(e.content for e in self._entries)
        return len(content) / self.memory_max if self.memory_max > 0 else 0


# ── Long-Term Memory ─────────────────────────────────────────────────────────

class LongTermMemory:
    """Persistent long-term memory with keyword indexing.

    Stores patterns, lessons, experiences, and skills.
    Can be upgraded to vector embeddings for semantic search.
    """

    def __init__(self):
        config = get_config().memory.long_term
        self.path = Path(config.path.replace("~", str(Path.home())))
        self.path.mkdir(parents=True, exist_ok=True)
        self._entries: List[MemoryEntry] = []
        self._load()

    def _load(self) -> None:
        index_file = self.path / "index.json"
        if index_file.exists():
            with open(index_file) as f:
                data = json.load(f)
                self._entries = [MemoryEntry(**e) for e in data.get("entries", [])]

    def _save(self) -> None:
        index_file = self.path / "index.json"
        with open(index_file, "w") as f:
            json.dump({
                "entries": [
                    {
                        "id": e.id,
                        "content": e.content,
                        "category": e.category,
                        "created_at": e.created_at,
                        "access_count": e.access_count,
                        "tags": e.tags,
                    }
                    for e in self._entries
                ],
                "updated_at": time.time(),
            }, f, indent=2)

    def store(self, content: str, category: str = "lesson", tags: Optional[List[str]] = None) -> MemoryEntry:
        entry = MemoryEntry(content=content, category=category, tags=tags or [])
        self._entries.append(entry)
        self._save()
        return entry

    def query(self, query: str, top_k: int = 5) -> List[MemoryEntry]:
        """Keyword-based search across long-term memory."""
        query_lower = query.lower()
        scored = []
        for entry in self._entries:
            score = 0
            if query_lower in entry.content.lower():
                score += len(query) / len(entry.content) if entry.content else 0
            for tag in entry.tags:
                if query_lower in tag.lower():
                    score += 0.5
            if score > 0:
                scored.append((score, entry))

        scored.sort(key=lambda x: -x[0])
        return [entry for _, entry in scored[:top_k]]

    def get_recent(self, n: int = 10) -> List[MemoryEntry]:
        return sorted(self._entries, key=lambda e: -e.created_at)[:n]

    def count(self) -> int:
        return len(self._entries)


# ── Memory Manager ───────────────────────────────────────────────────────────

class MemoryManager:
    """Orchestrates all memory layers."""

    def __init__(self):
        self.working = WorkingMemory()
        self.long_term = LongTermMemory()
        self.session = SessionContext()

    def get_system_prompt_block(self) -> str:
        """Get the full memory block for system prompt injection."""
        parts = [
            "══════════════════════════════════════════════",
            "PRAVIDHI MEMORY",
            "══════════════════════════════════════════════",
            "",
            self.working.get_formatted(),
            "",
            "══════════════════════════════════════════════",
            f"LONG-TERM MEMORY ({self.long_term.count()} entries)",
            "══════════════════════════════════════════════",
        ]
        recent = self.long_term.get_recent(5)
        for entry in recent:
            parts.append(f"• [{entry.category}] {entry.content[:200]}")

        return "\n".join(parts)

    def record_interaction(self, user_input: str, output: str = "") -> None:
        """Record an interaction in session context."""
        self.session.user_inputs.append(user_input)
        if output:
            self.session.assistant_outputs.append(output)

    def learn_from_interaction(
        self, user_input: str, output: str, success: bool, validation_score: float
    ) -> Optional[MemoryEntry]:
        """Extract and store lessons from an interaction."""
        if success and validation_score >= 0.9:
            return self.long_term.store(
                content=f"Successful pattern: {user_input[:100]} → {output[:200]}",
                category="learned_pattern",
                tags=[self._classify_input(user_input)],
            )
        return None

    def _classify_input(self, text: str) -> str:
        lower = text.lower()
        if any(w in lower for w in ["code", "function", "api", "script"]):
            return "code"
        if any(w in lower for w in ["deploy", "build", "run"]):
            return "devops"
        if any(w in lower for w in ["explain", "what", "how"]):
            return "question"
        return "general"
