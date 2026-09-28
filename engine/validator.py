"""Multi-layer validation engine — schema, behavioral, regression, and LLM-as-Judge.

Every response passes through these layers before being accepted.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, TypeAlias

logger = logging.getLogger("pravidhi.validator")


# ── Types ─────────────────────────────────────────────────────────────────────

ValidationResult: TypeAlias = bool
ValidationScore: TypeAlias = float


@dataclass
class ValidationReport:
    passed: bool
    layer: str
    score: ValidationScore = 1.0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationSuite:
    input_data: Dict[str, Any]
    output_data: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)


# ── Validator Protocol ────────────────────────────────────────────────────────

class Validator(Protocol):
    """Any validation layer must implement this protocol."""
    name: str

    def validate(self, suite: ValidationSuite) -> ValidationReport:
        ...


# ── Schema Validator ──────────────────────────────────────────────────────────

class SchemaValidator:
    """Validates tool input/output against JSON Schema."""
    name = "schema"

    def __init__(self, schemas: Optional[Dict[str, Dict]] = None):
        self.schemas = schemas or {}

    def register_schema(self, tool_name: str, schema: Dict) -> None:
        self.schemas[tool_name] = schema

    def validate(self, suite: ValidationSuite) -> ValidationReport:
        errors = []
        input_data = suite.input_data
        schema = self.schemas.get(input_data.get("tool", ""))

        if not schema:
            return ValidationReport(passed=True, layer=self.name)

        required = schema.get("required", [])
        properties = schema.get("properties", {})

        for field_name in required:
            if field_name not in input_data.get("params", {}):
                errors.append(f"Missing required field: {field_name}")

        for field_name, value in input_data.get("params", {}).items():
            field_schema = properties.get(field_name, {})
            field_type = field_schema.get("type", "")
            if field_type == "string" and not isinstance(value, str):
                errors.append(f"Field '{field_name}' should be string, got {type(value).__name__}")
            elif field_type == "integer" and not isinstance(value, int):
                errors.append(f"Field '{field_name}' should be integer, got {type(value).__name__}")

        return ValidationReport(
            passed=len(errors) == 0,
            layer=self.name,
            errors=errors,
            score=1.0 - (len(errors) * 0.1) if errors else 1.0,
        )


# ── Behavioral Validator (LLM-as-Judge) ──────────────────────────────────────

class BehavioralValidator:
    """Uses an LLM to judge whether output satisfies constraints."""
    name = "behavioral"

    def __init__(self, rules: Optional[List[str]] = None):
        self.rules = rules or []

    def add_rule(self, rule: str) -> None:
        self.rules.append(rule)

    async def validate(self, suite: ValidationSuite) -> ValidationReport:
        """Async validation using LLM-as-Judge pattern."""
        if not self.rules:
            return ValidationReport(passed=True, layer=self.name)

        # In practice, this sends to an LLM for judgment.
        # The structured prompt asks the judge model to score compliance.
        prompt = self._build_judge_prompt(suite)

        report = ValidationReport(
            passed=True,  # optimistic — overridden by LLM response
            layer=self.name,
            details={"judge_prompt": prompt},
        )

        # TODO: Integrate with provider_router for actual LLM call
        # response = await provider_router.chat(prompt)
        # report.passed = response.judgment.passed
        # report.score = response.judgment.score

        return report

    def _build_judge_prompt(self, suite: ValidationSuite) -> str:
        rules_text = "\n".join(f"- {r}" for r in self.rules)
        return f"""You are a validation judge. Determine if the following output satisfies ALL rules.

Rules:
{rules_text}

Input: {json.dumps(suite.input_data, indent=2)[:500]}
Output: {json.dumps(suite.output_data, indent=2)[:1000]}

Respond with JSON: {{"passed": bool, "score": float 0-1, "issues": [str]}}"""


# ── Regression Validator ──────────────────────────────────────────────────────

class RegressionValidator:
    """Checks output against known-good patterns from experience DB."""
    name = "regression"

    def __init__(self, pattern_db: Optional[Dict[str, List[Dict]]] = None):
        self.pattern_db = pattern_db or {}

    def learn_pattern(self, task_type: str, output: Dict) -> None:
        """Record a known-good output pattern."""
        if task_type not in self.pattern_db:
            self.pattern_db[task_type] = []
        self.pattern_db[task_type].append(output)
        # Keep only recent patterns
        if len(self.pattern_db[task_type]) > 100:
            self.pattern_db[task_type] = self.pattern_db[task_type][-100:]

    def validate(self, suite: ValidationSuite) -> ValidationReport:
        task_type = suite.input_data.get("task_type", "default")
        patterns = self.pattern_db.get(task_type, [])

        if not patterns:
            return ValidationReport(passed=True, layer=self.name, details={"no_patterns": True})

        output = suite.output_data
        warnings = []

        # Check structure consistency
        if patterns:
            ref_keys = set(patterns[0].keys())
            out_keys = set(output.keys())
            missing = ref_keys - out_keys
            if missing:
                warnings.append(f"Output missing expected keys: {missing}")

        return ValidationReport(
            passed=len(warnings) == 0,
            layer=self.name,
            warnings=warnings,
            score=1.0 - (len(warnings) * 0.15),
            details={"patterns_checked": len(patterns)},
        )


# ── Orchestrated Validation Pipeline ─────────────────────────────────────────

class ValidationEngine:
    """Orchestrates all validation layers in sequence."""

    def __init__(self):
        self.schema = SchemaValidator()
        self.behavioral = BehavioralValidator()
        self.regression = RegressionValidator()
        self._enabled_layers: Dict[str, bool] = {
            "schema": True,
            "behavioral": True,
            "regression": True,
        }

    def enable_layer(self, name: str, enabled: bool = True) -> None:
        if name in self._enabled_layers:
            self._enabled_layers[name] = enabled

    def add_behavioral_rule(self, rule: str) -> None:
        self.behavioral.add_rule(rule)

    async def validate(
        self,
        input_data: Dict[str, Any],
        output_data: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, ValidationReport]:
        """Run all enabled validation layers."""
        suite = ValidationSuite(
            input_data=input_data,
            output_data=output_data,
            metadata=metadata or {},
        )

        reports: Dict[str, ValidationReport] = {}

        for name in ["schema", "regression"]:
            if self._enabled_layers.get(name, False):
                validator = getattr(self, name)
                if hasattr(validator, "validate"):
                    reports[name] = validator.validate(suite)

        if self._enabled_layers.get("behavioral", False):
            reports["behavioral"] = await self.behavioral.validate(suite)

        return reports

    def overall_score(self, reports: Dict[str, ValidationReport]) -> float:
        """Compute weighted overall validation score."""
        if not reports:
            return 1.0
        weights = {"schema": 0.4, "behavioral": 0.4, "regression": 0.2}
        total = 0.0
        weight_sum = 0.0
        for layer, report in reports.items():
            w = weights.get(layer, 0.33)
            total += report.score * w
            weight_sum += w
        return total / weight_sum if weight_sum > 0 else 1.0

    def all_passed(self, reports: Dict[str, ValidationReport]) -> bool:
        return all(r.passed for r in reports.values())
