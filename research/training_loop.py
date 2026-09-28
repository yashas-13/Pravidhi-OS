"""Karpathy-style training loop for continuous self-improvement.

Every execution is treated as a training step:
- Forward pass = Execute task
- Backward pass = Analyze mistakes
- Loss = Failure rate
- Convergence = Accuracy > 95%
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, TypeAlias

logger = logging.getLogger("pravidhi.research")


# ── Data Types ────────────────────────────────────────────────────────────────

@dataclass
class TrainingStep:
    """A single execution logged as a training step."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: float = field(default_factory=time.time)
    prompt: str = ""
    intent_type: str = "general"
    provider: str = ""
    model: str = ""
    success: bool = False
    score: float = 0.0
    latency_ms: float = 0.0
    validation_score: float = 0.0
    error: Optional[str] = None
    patterns_found: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TrainingMetrics:
    """Aggregated training metrics."""
    total_steps: int = 0
    success_count: int = 0
    fail_count: int = 0
    accuracy: float = 0.0
    loss: float = 0.0
    avg_latency_ms: float = 0.0
    recent_scores: List[float] = field(default_factory=list)
    intent_breakdown: Dict[str, Dict] = field(default_factory=dict)
    convergence_reached: bool = False
    current_epoch: int = 0


@dataclass
class SkillDraft:
    """A skill generated from patterns."""
    name: str
    description: str
    content: str
    source: str = "auto_generated"  # mistake | success | request
    confidence: float = 0.0
    tags: List[str] = field(default_factory=list)


# ── Experience Database ───────────────────────────────────────────────────────

class ExperienceDB:
    """Persistent store for training steps and learned patterns.

    Uses JSON files for simplicity — can be upgraded to vector DB.
    """

    def __init__(self, base_path: str = "~/.pravidhi/experience/"):
        self.path = Path(base_path.replace("~", str(Path.home())))
        self.path.mkdir(parents=True, exist_ok=True)
        self.steps_file = self.path / "steps.jsonl"
        self.patterns_file = self.path / "patterns.json"
        self.lessons_file = self.path / "lessons.json"
        self._steps: List[TrainingStep] = []
        self._load()

    def _load(self) -> None:
        """Load existing data from disk."""
        if self.steps_file.exists():
            with open(self.steps_file) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            data = json.loads(line)
                            self._steps.append(TrainingStep(**data))
                        except (json.JSONDecodeError, TypeError):
                            pass

        if self.patterns_file.exists():
            with open(self.patterns_file) as f:
                self._patterns = json.load(f)
        else:
            self._patterns: Dict[str, List[Dict]] = {}

        if self.lessons_file.exists():
            with open(self.lessons_file) as f:
                self._lessons = json.load(f)
        else:
            self._lessons: List[Dict] = []

    def _save_steps(self) -> None:
        """Append new steps to JSONL."""
        with open(self.steps_file, "a") as f:
            for step in self._steps[-10:]:  # Save only recent unwritten
                f.write(json.dumps(step.__dict__, default=str) + "\n")

    def record_step(self, step: TrainingStep) -> None:
        """Record a training step."""
        self._steps.append(step)
        if len(self._steps) % 10 == 0:
            self._save_steps()

    def get_recent_steps(self, n: int = 100) -> List[TrainingStep]:
        """Get the N most recent steps."""
        return self._steps[-n:]

    def get_all_steps(self) -> List[TrainingStep]:
        return self._steps

    def store_pattern(self, task_type: str, pattern: Dict[str, Any]) -> None:
        """Store a learned pattern."""
        if task_type not in self._patterns:
            self._patterns[task_type] = []
        self._patterns[task_type].append({
            **pattern,
            "stored_at": time.time(),
        })
        with open(self.patterns_file, "w") as f:
            json.dump(self._patterns, f, indent=2, default=str)

    def store_lesson(self, lesson: Dict[str, Any]) -> None:
        """Store a lesson learned."""
        self._lessons.append({
            **lesson,
            "lesson_id": uuid.uuid4().hex[:8],
            "stored_at": time.time(),
        })
        with open(self.lessons_file, "w") as f:
            json.dump(self._lessons, f, indent=2, default=str)

    def query_similar(self, task_type: str, top_k: int = 5) -> List[Dict]:
        """Find similar patterns for a task type (keyword-based)."""
        results = []
        patterns = self._patterns.get(task_type, [])
        for p in patterns[-top_k:]:
            results.append(p)
        return results

    def get_metrics(self) -> TrainingMetrics:
        """Compute aggregate metrics from all steps."""
        recent = self._steps[-100:] if len(self._steps) > 100 else self._steps
        if not recent:
            return TrainingMetrics()

        successes = sum(1 for s in recent if s.success)
        total = len(recent)
        accuracy = successes / total if total > 0 else 0.0
        loss = 1.0 - accuracy

        # Intent breakdown
        intent_breakdown = defaultdict(lambda: {"count": 0, "success": 0})
        for s in recent:
            intent_breakdown[s.intent_type]["count"] += 1
            if s.success:
                intent_breakdown[s.intent_type]["success"] += 1

        avg_latency = sum(s.latency_ms for s in recent) / total if total > 0 else 0.0

        return TrainingMetrics(
            total_steps=len(self._steps),
            success_count=successes,
            fail_count=total - successes,
            accuracy=accuracy,
            loss=loss,
            avg_latency_ms=avg_latency,
            recent_scores=[s.score for s in recent[-20:]],
            intent_breakdown=dict(intent_breakdown),
            convergence_reached=accuracy >= 0.95,
        )

    def clear_old(self, max_steps: int = 10000) -> int:
        """Keep only the most recent steps."""
        if len(self._steps) > max_steps:
            trimmed = self._steps[-max_steps:]
            self._steps = trimmed
            self._save_steps()
            return len(self._steps)
        return len(self._steps)


# ── Pattern Detector ─────────────────────────────────────────────────────────

class PatternDetector:
    """Detects recurring patterns in execution history."""

    def __init__(self, db: ExperienceDB):
        self.db = db

    def detect_error_patterns(self, steps: List[TrainingStep]) -> List[Dict]:
        """Find recurring error patterns."""
        errors = [s for s in steps if not s.success and s.error]
        if len(errors) < 3:
            return []

        # Group similar errors
        error_groups: Dict[str, List[TrainingStep]] = {}
        for step in errors:
            key = step.error[:50] if step.error else "unknown"
            if key not in error_groups:
                error_groups[key] = []
            error_groups[key].append(step)

        patterns = []
        for error_text, group in error_groups.items():
            if len(group) >= 2:
                patterns.append({
                    "type": "recurring_error",
                    "error": error_text,
                    "count": len(group),
                    "percentage": len(group) / len(errors) * 100,
                    "examples": [s.prompt[:100] for s in group[:3]],
                    "severity": "high" if len(group) > 5 else "medium",
                })

        return patterns

    def detect_success_patterns(self, steps: List[TrainingStep]) -> List[Dict]:
        """Find patterns in highly successful executions."""
        successes = [s for s in steps if s.success and s.score >= 0.9]
        if len(successes) < 3:
            return []

        # Group by intent type + provider combo
        combo_groups: Dict[str, List[TrainingStep]] = defaultdict(list)
        for s in successes:
            key = f"{s.intent_type}::{s.provider}"
            combo_groups[key].append(s)

        patterns = []
        for combo, group in combo_groups.items():
            if len(group) >= 2:
                intent, provider = combo.split("::")
                patterns.append({
                    "type": "successful_combo",
                    "intent": intent,
                    "provider": provider,
                    "count": len(group),
                    "avg_score": sum(s.score for s in group) / len(group),
                    "avg_latency": sum(s.latency_ms for s in group) / len(group),
                })

        return patterns


# ── Skill Generator ──────────────────────────────────────────────────────────

class SkillGenerator:
    """Generates Codex-compatible skills from patterns."""

    def __init__(self, output_dir: str = "~/.codex/skills/"):
        self.output_dir = Path(output_dir.replace("~", str(Path.home())))
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_from_mistake(self, pattern: Dict) -> Optional[SkillDraft]:
        """Generate a fix-skill from a recurring error."""
        error_text = pattern.get("error", "")
        if not error_text:
            return None

        skill_name = f"fix-{error_text.split(':')[0].strip().lower()[:30]}"
        skill_name = "".join(c for c in skill_name if c.isalnum() or c in "-_").strip("-")

        return SkillDraft(
            name=skill_name,
            description=f"Fix for recurring error: {error_text[:80]}",
            content=self._build_fix_skill(error_text, pattern.get("examples", [])),
            source="mistake",
            confidence=min(pattern.get("count", 1) * 0.15, 0.95),
            tags=["auto-generated", "fix", "error-recovery"],
        )

    def generate_from_success(self, pattern: Dict) -> Optional[SkillDraft]:
        """Generate a pattern-skill from successful executions."""
        intent = pattern.get("intent", "")
        provider = pattern.get("provider", "")
        if not intent:
            return None

        skill_name = f"pattern-{intent}-{provider}".lower()[:40]
        skill_name = "".join(c for c in skill_name if c.isalnum() or c in "-_").strip("-")

        return SkillDraft(
            name=skill_name,
            description=f"Proven pattern for {intent} tasks using {provider}",
            content=self._build_pattern_skill(intent, provider, pattern),
            source="success",
            confidence=min(pattern.get("avg_score", 0), 0.95),
            tags=["auto-generated", "pattern", intent],
        )

    def save_skill(self, draft: SkillDraft) -> Optional[Path]:
        """Write a skill to disk as a Codex-compatible SKILL.md."""
        if not draft.name:
            return None

        skill_dir = self.output_dir / draft.name
        skill_dir.mkdir(parents=True, exist_ok=True)

        content = f"""---
name: {draft.name}
description: >
  {draft.description}
  Auto-generated by Pravidhi — confidence: {draft.confidence:.0%}
  Source: {draft.source}
tags: [{', '.join(draft.tags)}]
---

# {draft.name}

{draft.content}

## Metadata

- Generated: {datetime.utcnow().isoformat()}
- Source: {draft.source}
- Confidence: {draft.confidence:.0%}
- Use Count: 0
"""
        skill_file = skill_dir / "SKILL.md"
        with open(skill_file, "w") as f:
            f.write(content)

        logger.info(f"Generated skill: {draft.name} ({draft.source}, {draft.confidence:.0%})")
        return skill_file

    def _build_fix_skill(self, error: str, examples: List[str]) -> str:
        examples_text = "\n".join(f"- {ex}" for ex in examples[:3])
        return f"""## Description

This skill helps fix a recurring error pattern detected by Pravidhi's auto-research engine.

## Error Pattern

```
{error}
```

## Examples

{examples_text}

## Resolution Steps

1. Identify the root cause of this error pattern
2. Apply the known fix verified by Pravidhi's training history
3. Validate the fix passes all test cases
4. Record the outcome for the next research cycle
"""

    def _build_pattern_skill(self, intent: str, provider: str, pattern: Dict) -> str:
        return f"""## Description

Proven pattern for {intent} tasks using {provider}, discovered by Pravidhi's auto-research engine.

## Performance

- Success Rate: {pattern.get('avg_score', 0):.0%}
- Average Latency: {pattern.get('avg_latency', 0):.0f}ms
- Times Validated: {pattern.get('count', 0)}

## Workflow

1. Use {provider} as the primary provider for {intent} tasks
2. Follow the standard pipeline: ingest → validate → route → execute
3. Apply Pravidhi's multi-layer validation to verify output
4. Record the execution for continuous improvement
"""


# ── Training Loop ────────────────────────────────────────────────────────────

class TrainingLoop:
    """Karpathy-inspired training loop — continuous self-improvement."""

    def __init__(self, db: Optional[ExperienceDB] = None):
        self.db = db or ExperienceDB()
        self.pattern_detector = PatternDetector(self.db)
        self.skill_generator = SkillGenerator()
        self._epoch = 0
        self._converged = False

    async def record_step(self, step: TrainingStep) -> None:
        """Record one training step (forward pass)."""
        self.db.record_step(step)

    async def run_analysis(self) -> Dict[str, Any]:
        """Run one analysis cycle (backward pass)."""
        self._epoch += 1
        recent = self.db.get_recent_steps(100)
        metrics = self.db.get_metrics()

        logger.info(
            f"Research cycle E{self._epoch}: "
            f"accuracy={metrics.accuracy:.1%}, "
            f"loss={metrics.loss:.3f}, "
            f"steps={metrics.total_steps}"
        )

        # Calculate loss
        if metrics.total_steps > 0:
            metrics.loss = 1.0 - metrics.accuracy

        # Check convergence
        if metrics.accuracy >= 0.95:
            self._converged = True
            logger.info(f"✓ CONVERGED at epoch {self._epoch} (accuracy={metrics.accuracy:.1%})")

        # Analyze patterns
        error_patterns = self.pattern_detector.detect_error_patterns(recent)
        success_patterns = self.pattern_detector.detect_success_patterns(recent)

        # Generate skills
        skills_generated = []
        for pattern in error_patterns:
            draft = self.skill_generator.generate_from_mistake(pattern)
            if draft:
                path = self.skill_generator.save_skill(draft)
                if path:
                    skills_generated.append(draft.name)

        for pattern in success_patterns:
            draft = self.skill_generator.generate_from_success(pattern)
            if draft:
                path = self.skill_generator.save_skill(draft)
                if path:
                    skills_generated.append(draft.name)

        # Store lessons
        if error_patterns:
            self.db.store_lesson({
                "epoch": self._epoch,
                "type": "error_analysis",
                "patterns": error_patterns,
                "skills_generated": skills_generated,
            })

        return {
            "epoch": self._epoch,
            "accuracy": metrics.accuracy,
            "loss": metrics.loss,
            "converged": self._converged,
            "total_steps": metrics.total_steps,
            "error_patterns_found": len(error_patterns),
            "success_patterns_found": len(success_patterns),
            "skills_generated": skills_generated,
            "intent_breakdown": metrics.intent_breakdown,
        }

    async def practice_loop(
        self, prompt: str, epochs: int = 5
    ) -> List[Dict[str, Any]]:
        """Iterative practice-perfect execution loop."""
        results = []
        for epoch in range(1, epochs + 1):
            start = time.time()

            # Execute with current best strategy
            from engine.provider_router import ProviderRouter
            router = ProviderRouter()
            response = await router.chat(
                messages=[{"role": "user", "content": prompt}]
            )

            duration = (time.time() - start) * 1000
            success = "error" not in response

            step = TrainingStep(
                prompt=prompt,
                intent_type="practice",
                provider=response.get("provider", "unknown"),
                model=response.get("model", "unknown"),
                success=success,
                score=0.8 if success else 0.0,
                latency_ms=duration,
            )
            self.db.record_step(step)

            epoch_result = {
                "epoch": epoch,
                "success": success,
                "duration_ms": duration,
                "score": step.score,
            }
            results.append(epoch_result)

            logger.info(f"Practice E{epoch}: {'✓' if success else '✗'} ({duration:.0f}ms)")

            if success and epoch >= 3:
                # Check if we've converged
                recent = self.db.get_recent_steps(10)
                if recent and all(s.success for s in recent[-3:]):
                    logger.info(f"✓ CONVERGED after {epoch} practice epochs")
                    break

        return results

    def get_status(self) -> Dict[str, Any]:
        """Get current training status."""
        metrics = self.db.get_metrics()
        return {
            "current_epoch": self._epoch,
            "converged": self._converged,
            "accuracy": metrics.accuracy,
            "loss": metrics.loss,
            "total_steps": metrics.total_steps,
            "success_count": metrics.success_count,
            "fail_count": metrics.fail_count,
            "avg_latency_ms": metrics.avg_latency_ms,
            "intent_breakdown": metrics.intent_breakdown,
        }


# ── Auto-Research Cycle (for cron integration) ────────────────────────────────

async def run_research_cycle() -> Dict[str, Any]:
    """Full auto-research cycle — callable from cron jobs."""
    loop = TrainingLoop()
    return await loop.run_analysis()
