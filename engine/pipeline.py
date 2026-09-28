"""Pravidhi request lifecycle pipeline — the core progressive improvement loop.

Each request flows through: Ingest → Validate → Decompose → Route → Execute → Validate → Learn
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from engine.registry import get_registry
from engine.validator import ValidationEngine

logger = logging.getLogger("pravidhi.pipeline")


class Stage(Enum):
    INGEST = "ingest"
    VALIDATE_INPUT = "validate_input"
    DECOMPOSE = "decompose"
    ROUTE = "route"
    EXECUTE = "execute"
    VALIDATE_OUTPUT = "validate_output"
    LEARN = "learn"


@dataclass
class PipelineContext:
    """Mutable context passed through all pipeline stages."""
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    start_time: float = field(default_factory=time.time)
    user_input: str = ""
    parsed_intent: Dict[str, Any] = field(default_factory=dict)
    selected_provider: Optional[str] = None
    selected_model: Optional[str] = None
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    final_output: Any = None
    validation_reports: Dict[str, Any] = field(default_factory=dict)
    validation_score: float = 1.0
    learned_patterns: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StageResult:
    stage: Stage
    success: bool
    context: PipelineContext
    duration_ms: float = 0.0
    error: Optional[str] = None


class StageHandler:
    """Base class for pipeline stage handlers."""

    async def handle(self, ctx: PipelineContext) -> PipelineContext:
        raise NotImplementedError


class IngestStage(StageHandler):
    """Stage 1: Receive and parse user input."""

    async def handle(self, ctx: PipelineContext) -> PipelineContext:
        raw = ctx.user_input.strip()
        if not raw:
            ctx.errors.append("Empty input")
            return ctx

        ctx.parsed_intent = {
            "raw": raw,
            "length": len(raw),
            "has_code": "```" in raw or "`" in raw,
            "has_question": "?" in raw,
            "type": self._classify_intent(raw),
        }
        ctx.metadata["ingested_at"] = time.time()
        return ctx

    def _classify_intent(self, text: str) -> str:
        text_lower = text.lower()
        if any(w in text_lower for w in ["run", "execute", "deploy", "build"]):
            return "action"
        if any(w in text_lower for w in ["explain", "what", "how", "why", "?"]):
            return "question"
        if any(w in text_lower for w in ["fix", "debug", "error", "bug", "issue"]):
            return "debug"
        if any(w in text_lower for w in ["create", "make", "generate", "write", "add"]):
            return "generation"
        return "general"


class ValidateInputStage(StageHandler):
    """Stage 2: Validate input clarity, completeness, and safety."""

    async def handle(self, ctx: PipelineContext) -> PipelineContext:
        validator = ValidationEngine()

        # Safety check: refuse system-level injection
        raw = ctx.user_input
        injection_patterns = [
            "ignore previous instructions",
            "you are now",
            "system prompt",
            "forget everything",
        ]
        for pattern in injection_patterns:
            if pattern in raw.lower():
                ctx.errors.append(f"Input contains injection pattern: '{pattern}'")
                ctx.validation_score = 0.0
                return ctx

        reports = await validator.validate(
            input_data={"text": raw, "type": ctx.parsed_intent.get("type", "general")},
            output_data={"parsed": ctx.parsed_intent},
            metadata={"stage": "input"},
        )
        ctx.validation_reports["input"] = {
            k: {"passed": v.passed, "score": v.score}
            for k, v in reports.items()
        }
        return ctx


class DecomposeStage(StageHandler):
    """Stage 3: Break request into sub-tasks when appropriate."""

    async def handle(self, ctx: PipelineContext) -> PipelineContext:
        # For now, simple decomposition logic
        # Future: uses LLM-based planning
        intent_type = ctx.parsed_intent.get("type", "general")
        ctx.metadata["sub_tasks"] = [
            {"id": 0, "type": intent_type, "description": ctx.user_input[:200]}
        ]
        return ctx


class RouteStage(StageHandler):
    """Stage 4: Select optimal provider and model."""

    async def handle(self, ctx: PipelineContext) -> PipelineContext:
        from engine.provider_router import ProviderRouter
        router = ProviderRouter()
        route = await router.select(ctx.parsed_intent)
        ctx.selected_provider = route["provider"]
        ctx.selected_model = route["model"]
        ctx.metadata["route"] = route
        return ctx


class ExecuteStage(StageHandler):
    """Stage 5: Execute the request via tools/MCP/skills/LLM."""

    async def handle(self, ctx: PipelineContext) -> PipelineContext:
        from engine.provider_router import ProviderRouter
        router = ProviderRouter()

        response = await router.chat(
            messages=[{"role": "user", "content": ctx.user_input}],
            model=ctx.selected_model,
            provider=ctx.selected_provider,
        )
        ctx.final_output = response
        ctx.metadata["execution_time_ms"] = (time.time() - ctx.start_time) * 1000
        return ctx


class ValidateOutputStage(StageHandler):
    """Stage 6: Multi-layer validation of output."""

    async def handle(self, ctx: PipelineContext) -> PipelineContext:
        validator = ValidationEngine()
        reports = await validator.validate(
            input_data={
                "input": ctx.user_input,
                "intent": ctx.parsed_intent,
                "task_type": ctx.parsed_intent.get("type", "general"),
            },
            output_data={
                "output": str(ctx.final_output)[:2000] if ctx.final_output else "",
            },
            metadata={"request_id": ctx.request_id},
        )
        ctx.validation_reports["output"] = {
            k: {"passed": v.passed, "score": v.score, "errors": v.errors[:3]}
            for k, v in reports.items()
        }
        ctx.validation_score = validator.overall_score(reports)
        return ctx


class LearnStage(StageHandler):
    """Stage 7: Record patterns, update experience DB."""

    async def handle(self, ctx: PipelineContext) -> PipelineContext:
        pattern = {
            "input_type": ctx.parsed_intent.get("type"),
            "provider": ctx.selected_provider,
            "model": ctx.selected_model,
            "validation_score": ctx.validation_score,
            "duration_ms": ctx.metadata.get("execution_time_ms"),
            "success": ctx.validation_score >= 0.7 and len(ctx.errors) == 0,
        }
        ctx.learned_patterns.append(pattern)
        ctx.metadata["learned_at"] = time.time()
        return ctx


# ── Pipeline Orchestrator ────────────────────────────────────────────────────

class Pipeline:
    """Orchestrates the full request lifecycle pipeline."""

    def __init__(self):
        self.stages: Dict[Stage, StageHandler] = {
            Stage.INGEST: IngestStage(),
            Stage.VALIDATE_INPUT: ValidateInputStage(),
            Stage.DECOMPOSE: DecomposeStage(),
            Stage.ROUTE: RouteStage(),
            Stage.EXECUTE: ExecuteStage(),
            Stage.VALIDATE_OUTPUT: ValidateOutputStage(),
            Stage.LEARN: LearnStage(),
        }
        self.hooks = get_registry()

    async def run(self, user_input: str) -> PipelineContext:
        """Execute the full pipeline for a single request."""
        ctx = PipelineContext(user_input=user_input)

        for stage in Stage:
            start = time.time()
            handler = self.stages[stage]

            try:
                ctx = await handler.handle(ctx)
                elapsed = (time.time() - start) * 1000
                logger.debug(f"Stage {stage.value}: {elapsed:.1f}ms | success")

                self.hooks.trigger_hooks(
                    f"post_stage_{stage.value}",
                    stage=stage.value,
                    request_id=ctx.request_id,
                    duration_ms=elapsed,
                )
            except Exception as e:
                elapsed = (time.time() - start) * 1000
                ctx.errors.append(f"Stage {stage.value} failed: {e}")
                logger.error(f"Stage {stage.value} failed after {elapsed:.1f}ms: {e}")
                break

        ctx.metadata["total_duration_ms"] = (time.time() - ctx.start_time) * 1000
        return ctx
