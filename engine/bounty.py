"""Vibe Buy Bounty System — Community feature bounty marketplace.

A bounty system where users can:
- Post bounties for features, fixes, or improvements
- Claim bounties to work on them
- Submit completions for review
- Track earnings and reputation
- Browse available and completed bounties

Inspired by Gitcoin, Bounty, and Dora ecosystem patterns.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("pravidhi.bounty")

BOUNTY_STATUS = ["open", "claimed", "in_progress", "completed", "cancelled", "verified"]
BOUNTY_CATEGORIES = [
    "feature", "bugfix", "enhancement", "security", "documentation",
    "integration", "skill", "plugin", "mcp", "tool", "ui_ux", "other",
]
BOUNTY_SEVERITY = ["low", "medium", "high", "critical"]
BOUNTY_REWARDS = ["usd", "token", "reputation", "nft", "vibe"]


@dataclass
class Bounty:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    title: str = ""
    description: str = ""
    category: str = "feature"
    severity: str = "medium"
    reward_type: str = "vibe"
    reward_amount: float = 0.0
    reward_currency: str = "VIBE"
    status: str = "open"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    created_by: str = "system"
    claimed_by: str = ""
    claimed_at: float = 0.0
    completed_at: float = 0.0
    submission_notes: str = ""
    tags: list[str] = field(default_factory=list)
    requirements: list[str] = field(default_factory=list)
    skills_needed: list[str] = field(default_factory=list)
    repo_url: str = ""
    pr_url: str = ""


@dataclass
class BountyHunter:
    username: str = ""
    display_name: str = ""
    reputation: float = 0.0
    vibe_earned: float = 0.0
    bounties_completed: int = 0
    bounties_posted: int = 0
    joined_at: float = field(default_factory=time.time)
    skills: list[str] = field(default_factory=list)
    badges: list[str] = field(default_factory=list)


class BountyBoard:
    def __init__(self, db_path: str | None = None):
        self.db_path = Path(db_path or os.path.expanduser("~/.pravidhi/bounties.json"))
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.bounties: dict[str, Bounty] = {}
        self.hunters: dict[str, BountyHunter] = {}
        self._lock = asyncio.Lock()
        self._load()

    def _load(self):
        if self.db_path.exists():
            try:
                data = json.loads(self.db_path.read_text())
                for b_data in data.get("bounties", []):
                    self.bounties[b_data["id"]] = Bounty(**b_data)
                for h_data in data.get("hunters", []):
                    self.hunters[h_data["username"]] = BountyHunter(**h_data)
            except Exception as e:
                logger.error(f"Failed to load bounties: {e}")

    def _save(self):
        try:
            data = {
                "bounties": [vars(b) for b in self.bounties.values()],
                "hunters": [vars(h) for h in self.hunters.values()],
                "updated_at": time.time(),
            }
            self.db_path.write_text(json.dumps(data, indent=2, default=str))
        except Exception as e:
            logger.error(f"Failed to save bounties: {e}")

    async def create_bounty(self, title: str, description: str = "",
                            category: str = "feature",
                            reward_type: str = "vibe",
                            reward_amount: float = 0,
                            created_by: str = "system",
                            severity: str = "medium",
                            tags: list[str] | None = None,
                            requirements: list[str] | None = None,
                            skills_needed: list[str] | None = None) -> Bounty:
        async with self._lock:
            bounty = Bounty(
                title=title, description=description,
                category=category if category in BOUNTY_CATEGORIES else "other",
                severity=severity if severity in BOUNTY_SEVERITY else "medium",
                reward_type=reward_type if reward_type in BOUNTY_REWARDS else "vibe",
                reward_amount=reward_amount, created_by=created_by,
                tags=tags or [], requirements=requirements or [],
                skills_needed=skills_needed or [],
            )
            self.bounties[bounty.id] = bounty
            self._save()
            return bounty

    async def claim_bounty(self, bounty_id: str, hunter: str) -> tuple[bool, str]:
        async with self._lock:
            bounty = self.bounties.get(bounty_id)
            if not bounty: return False, "Bounty not found"
            if bounty.status != "open": return False, f"Bounty is {bounty.status}, not open"
            bounty.status = "claimed"
            bounty.claimed_by = hunter
            bounty.claimed_at = time.time()
            bounty.updated_at = time.time()
            if hunter not in self.hunters:
                self.hunters[hunter] = BountyHunter(username=hunter)
            self._save()
            return True, f"Bounty {bounty_id[:8]} claimed by {hunter}"

    async def submit_completion(self, bounty_id: str, hunter: str,
                                 notes: str = "", pr_url: str = "") -> tuple[bool, str]:
        async with self._lock:
            bounty = self.bounties.get(bounty_id)
            if not bounty: return False, "Bounty not found"
            if bounty.claimed_by != hunter: return False, f"Claimed by {bounty.claimed_by}"
            if bounty.status not in ("claimed", "in_progress"):
                return False, f"Bounty is {bounty.status}"
            bounty.status = "completed"
            bounty.submission_notes = notes
            bounty.pr_url = pr_url
            bounty.completed_at = time.time()
            bounty.updated_at = time.time()
            if hunter in self.hunters:
                h = self.hunters[hunter]
                h.bounties_completed += 1
                h.vibe_earned += bounty.reward_amount
                h.reputation += self._calc_reputation(bounty)
            self._save()
            return True, f"Bounty {bounty_id[:8]} completed by {hunter}"

    async def list_bounties(self, status: str = "", category: str = "",
                             hunter: str = "") -> list[dict]:
        results = []
        for b in self.bounties.values():
            if status and b.status != status: continue
            if category and b.category != category: continue
            if hunter and b.claimed_by != hunter: continue
            results.append({
                "id": b.id[:8], "title": b.title,
                "description": b.description[:200], "category": b.category,
                "severity": b.severity,
                "reward": f"{b.reward_amount} {b.reward_currency}",
                "reward_type": b.reward_type, "status": b.status,
                "created_at": datetime.fromtimestamp(b.created_at).isoformat(),
                "created_by": b.created_by, "claimed_by": b.claimed_by,
                "tags": b.tags, "skills_needed": b.skills_needed,
            })
        return sorted(results, key=lambda x: x.get("created_at", ""), reverse=True)

    async def get_stats(self) -> dict:
        total = len(self.bounties)
        by_status: dict[str, int] = {}
        total_rewards = 0.0
        for b in self.bounties.values():
            by_status[b.status] = by_status.get(b.status, 0) + 1
            if b.status == "verified":
                total_rewards += b.reward_amount
        return {
            "total_bounties": total, "by_status": by_status,
            "total_rewards_paid": round(total_rewards, 1),
            "active_hunters": len(self.hunters),
            "open_bounties": by_status.get("open", 0),
            "completed_bounties": by_status.get("completed", 0) + by_status.get("verified", 0),
        }

    async def get_hunter_stats(self, username: str) -> dict | None:
        h = self.hunters.get(username)
        if not h: return None
        return {
            "username": h.username, "display_name": h.display_name or h.username,
            "reputation": round(h.reputation, 1),
            "vibe_earned": round(h.vibe_earned, 1),
            "bounties_completed": h.bounties_completed,
            "skills": h.skills, "badges": h.badges,
            "joined": datetime.fromtimestamp(h.joined_at).isoformat(),
        }

    def _calc_reputation(self, bounty: Bounty) -> float:
        base = {"low": 1.0, "medium": 5.0, "high": 25.0, "critical": 100.0}.get(bounty.severity, 1.0)
        return base + (bounty.reward_amount * 0.1)


async def execute_bounty(action: str = "list", **params) -> dict:
    board = BountyBoard()
    if action in ("list", "ls", "show", "browse"):
        bounties = await board.list_bounties(
            params.get("status", "open"),
            params.get("category", ""),
            params.get("hunter", ""),
        )
        stats = await board.get_stats()
        return {"type": "bounty_list", "bounties": bounties[:20], "total": len(bounties), "stats": stats}
    elif action in ("create", "add", "new"):
        b = await board.create_bounty(
            title=params.get("title", "Untitled"),
            description=params.get("description", ""),
            category=params.get("category", "feature"),
            reward_amount=params.get("reward_amount", 0),
            created_by=params.get("created_by", "anonymous"),
            severity=params.get("severity", "medium"),
            tags=params.get("tags", []),
            skills_needed=params.get("skills_needed", []),
        )
        return {"type": "bounty_created", "id": b.id[:8], "title": b.title,
                "reward": f"{b.reward_amount} {b.reward_currency}", "status": b.status}
    elif action in ("claim", "take"):
        success, msg = await board.claim_bounty(params.get("id",""), params.get("hunter","anonymous"))
        return {"type": "bounty_claim", "success": success, "message": msg}
    elif action in ("complete", "submit"):
        success, msg = await board.submit_completion(
            params.get("id",""), params.get("hunter",""),
            params.get("notes",""), params.get("pr_url",""),
        )
        return {"type": "bounty_submit", "success": success, "message": msg}
    elif action in ("stats", "status"):
        return {"type": "bounty_stats", "stats": await board.get_stats()}
    elif action in ("hunter", "profile"):
        profile = await board.get_hunter_stats(params.get("hunter",""))
        if profile: return {"type": "bounty_hunter", "profile": profile}
        return {"type": "error", "message": "Hunter not found"}
    return {"type": "bounty_help", "message": "Usage: bounty [list|create|claim|complete|stats|hunter]"}

_bounty_board: BountyBoard | None = None

def get_bounty_board() -> BountyBoard:
    global _bounty_board
    if _bounty_board is None:
        _bounty_board = BountyBoard()
    return _bounty_board
