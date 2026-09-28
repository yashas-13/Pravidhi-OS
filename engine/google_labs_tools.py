"""Pravidhi tools for all google-labs/design.md skills and tools.

Integrates:
1. DESIGN.md — lint, diff, export, spec
2. Agent DX CLI Scale — evaluate CLIs for AI agents
3. @json-render/ink — terminal UI rendering from JSON
4. TDD Red-Green-Refactor — disciplined TDD workflow
5. Typed Service Contracts — Spec & Handler pattern
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, TypeAlias

from engine.registry import get_registry

logger = logging.getLogger("pravidhi.google_labs")


# ═══════════════════════════════════════════════════════════════════════════════
# 1. DESIGN.md — Token-Based Design System
# ═══════════════════════════════════════════════════════════════════════════════

DESIGN_MD_SPEC_SCHEMA = {
    "colors": {"primary": "str", "secondary": "str", "tertiary": "str", "neutral": "str"},
    "typography": {
        "h1": {"fontFamily": "str", "fontSize": "str"},
        "body": {"fontFamily": "str", "fontSize": "str"},
    },
    "rounded": {"sm": "str", "md": "str"},
    "spacing": {"sm": "str", "md": "str"},
    "components": {"*": {"backgroundColor": "str", "textColor": "str", "rounded": "str", "padding": "str"}},
}

DESIGN_MD_LINT_RULES = [
    "broken-ref", "missing-primary", "contrast-ratio",
    "orphaned-tokens", "token-summary", "missing-sections",
    "missing-typography", "section-order", "unknown-key",
]


def parse_design_md(content: str) -> Dict[str, Any]:
    """Parse a DESIGN.md file extracting YAML front matter and body."""
    result = {"front_matter": {}, "body": "", "sections": {}, "errors": []}

    # Extract YAML front matter between --- fences
    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", content, re.DOTALL)
    if not fm_match:
        result["errors"].append("No valid YAML front matter found")
        return result

    yaml_text = fm_match.group(1)
    result["body"] = fm_match.group(2)

    # Parse YAML (simple key-value parser, no yaml dep needed)
    result["front_matter"] = _parse_yaml_simple(yaml_text)

    # Extract ## sections from body
    sections = re.findall(r"^##\s+(.+?)\n(.*?)(?=^##|\Z)", result["body"], re.MULTILINE | re.DOTALL)
    for title, body in sections:
        result["sections"][title.strip()] = body.strip()

    return result


def _parse_yaml_simple(text: str) -> Dict[str, Any]:
    """Simple nested YAML parser for DESIGN.md tokens."""
    result = {}
    current = result
    stack = []
    indent_levels = [0]

    for line in text.split("\n"):
        if not line.strip() or line.strip().startswith("#"):
            continue

        stripped = line.lstrip()
        indent = len(line) - len(stripped)

        while stack and indent <= indent_levels[-1]:
            current = stack.pop()
            indent_levels.pop()

        if ":" in stripped:
            key, _, value = stripped.partition(":")
            key = key.strip()
            value = value.strip()

            if value == "":
                # New nested section
                new_dict = {}
                if isinstance(current, dict):
                    current[key] = new_dict
                stack.append(current)
                current = new_dict
                indent_levels.append(indent)
            else:
                if isinstance(current, dict):
                    # Try to parse value as a number
                    try:
                        if "." in value:
                            value = float(value)
                        else:
                            value = int(value)
                    except ValueError:
                        pass
                    # Unquote
                    value = value.strip('"').strip("'")
                    current[key] = value

    return result


def lint_design_md(content: str) -> Dict[str, Any]:
    """Lint a DESIGN.md file against the spec.

    Returns structured findings similar to @google/design.md lint.
    """
    parsed = parse_design_md(content)
    findings = []
    fm = parsed.get("front_matter", {})

    # Rule: missing-primary
    colors = fm.get("colors", {})
    if isinstance(colors, dict) and "primary" not in colors:
        findings.append({
            "rule": "missing-primary", "severity": "warning",
            "message": "No 'primary' color defined — agents will auto-generate one",
        })

    # Rule: missing-typography
    if "typography" not in fm:
        findings.append({
            "rule": "missing-typography", "severity": "warning",
            "message": "No typography tokens defined — agents will use default fonts",
        })

    # Rule: broken-ref
    all_tokens = _collect_tokens(fm)
    body = parsed.get("body", "")
    refs = re.findall(r"\{([^}]+)\}", body)
    for ref in refs:
        parts = ref.split(".")
        current = fm
        found = True
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                found = False
                break
        if not found:
            findings.append({
                "rule": "broken-ref", "severity": "error",
                "message": f"Token reference '{{{ref}}}' does not resolve to any defined token",
            })

    # Rule: contrast-ratio (simple check)
    components = fm.get("components", {})
    if isinstance(components, dict):
        for comp_name, comp_tokens in components.items():
            if isinstance(comp_tokens, dict):
                bg = comp_tokens.get("backgroundColor", "")
                fg = comp_tokens.get("textColor", "")
                if bg and fg:
                    ratio = _wcag_contrast_ratio(bg, fg)
                    if ratio is not None and ratio < 4.5:
                        findings.append({
                            "rule": "contrast-ratio", "severity": "warning",
                            "message": f"Component '{comp_name}': {fg} on {bg} has contrast ratio {ratio:.1f}:1 — below WCAG AA minimum (4.5:1)",
                        })

    # Rule: orphaned-tokens
    if isinstance(colors, dict):
        color_refs = set(re.findall(r"\{colors\.([^}]+)\}", body))
        for name in colors:
            if name not in color_refs and name not in ("primary", "secondary", "tertiary", "neutral"):
                findings.append({
                    "rule": "orphaned-tokens", "severity": "warning",
                    "message": f"Color '{name}' defined but never referenced by any component",
                })

    # Rule: section-order
    section_order = ["Overview", "Colors", "Typography", "Layout", "Elevation", "Shapes", "Components", "Do's and Don'ts"]
    sections = parsed.get("sections", {})
    seen = []
    for sec in section_order:
        for s in sections:
            if sec.lower() in s.lower() and s not in seen:
                seen.append(s)

    # Rule: token-summary
    token_count = len(_collect_tokens(fm))
    findings.append({
        "rule": "token-summary", "severity": "info",
        "message": f"Defined {token_count} design tokens across {len(sections)} sections",
    })

    errors = [f for f in findings if f["severity"] == "error"]
    warnings = [f for f in findings if f["severity"] == "warning"]
    infos = [f for f in findings if f["severity"] == "info"]

    return {
        "findings": findings,
        "summary": {"errors": len(errors), "warnings": len(warnings), "info": len(infos)},
        "valid": len(errors) == 0,
    }


def diff_design_md(before: str, after: str) -> Dict[str, Any]:
    """Compare two DESIGN.md files and report token-level changes."""
    before_parsed = parse_design_md(before)
    after_parsed = parse_design_md(after)

    before_tokens = _collect_tokens(before_parsed.get("front_matter", {}))
    after_tokens = _collect_tokens(after_parsed.get("front_matter", {}))

    added = set(after_tokens.keys()) - set(before_tokens.keys())
    removed = set(before_tokens.keys()) - set(after_tokens.keys())
    modified = {
        k: {"before": before_tokens[k], "after": after_tokens[k]}
        for k in before_tokens if k in after_tokens and before_tokens[k] != after_tokens[k]
    }

    return {
        "tokens": {
            "added": sorted(added),
            "removed": sorted(removed),
            "modified": list(modified.keys()),
        },
        "changes": modified,
        "regression": len(removed) > 0 or len(modified) > 0,
    }


def export_design_md(content: str, fmt: str = "json-tailwind") -> str:
    """Export DESIGN.md tokens to another format."""
    parsed = parse_design_md(content)
    fm = parsed.get("front_matter", {})
    colors = fm.get("colors", {})
    typography = fm.get("typography", {})
    rounded = fm.get("rounded", {})
    spacing = fm.get("spacing", {})

    if fmt == "json-tailwind":
        export = {"theme": {"extend": {}}}
        if colors:
            export["theme"]["extend"]["colors"] = colors
        if isinstance(typography, dict):
            export["theme"]["extend"]["fontFamily"] = {
                k: v.get("fontFamily", []) for k, v in typography.items() if isinstance(v, dict)
            }
        return json.dumps(export, indent=2)

    elif fmt == "css-tailwind":
        lines = ["@theme {"]
        for name, val in (colors if isinstance(colors, dict) else {}).items():
            lines.append(f'  --color-{name}: {val};')
        for name, val in (rounded if isinstance(rounded, dict) else {}).items():
            lines.append(f'  --radius-{name}: {val};')
        for name, val in (spacing if isinstance(spacing, dict) else {}).items():
            lines.append(f'  --spacing-{name}: {val};')
        lines.append("}")
        return "\n".join(lines)

    elif fmt == "dtcg":
        dtcg = {}
        for name, val in (colors if isinstance(colors, dict) else {}).items():
            dtcg[f"color/{name}"] = {"$value": val, "$type": "color"}
        return json.dumps(dtcg, indent=2)

    return ""


def _wcag_contrast_ratio(bg: str, fg: str) -> Optional[float]:
    """Approximate WCAG contrast ratio between two CSS colors."""
    def _relative_luminance(hex_color: str) -> float:
        hex_color = hex_color.lstrip("#")
        if len(hex_color) != 6:
            return 0.0
        r, g, b = [int(hex_color[i:i+2], 16) / 255.0 for i in (0, 2, 4)]
        r = r / 12.92 if r <= 0.03928 else ((r + 0.055) / 1.055) ** 2.4
        g = g / 12.92 if g <= 0.03928 else ((g + 0.055) / 1.055) ** 2.4
        b = b / 12.92 if b <= 0.03928 else ((b + 0.055) / 1.055) ** 2.4
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    l1 = _relative_luminance(bg)
    l2 = _relative_luminance(fg)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05) if darker >= 0 else None


def _collect_tokens(obj: Any, prefix: str = "") -> Dict[str, Any]:
    """Flatten nested dict to dot-separated keys."""
    tokens = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                tokens.update(_collect_tokens(v, key))
            else:
                tokens[key] = v
    return tokens


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Agent DX CLI Scale
# ═══════════════════════════════════════════════════════════════════════════════

CLI_SCALE_AXES = [
    "machine_readable_output",
    "raw_payload_input",
    "deterministic_editing",
    "error_defense_in_depth",
    "stateless_idempotent",
    "explicit_control_flow",
    "tool_discovery",
]

CLI_SCALE_CRITERIA = {
    "machine_readable_output": {
        0: "Human-only output (tables, color codes, prose). No structured format available.",
        1: "--output json or equivalent exists but is incomplete or inconsistent.",
        2: "Consistent JSON output across all commands. Errors also return structured JSON.",
        3: "NDJSON streaming for paginated results. Structured output is default in non-TTY.",
    },
    "raw_payload_input": {
        0: "Only interactive prompts or multi-word flags. No stdin input support.",
        1: "Accepts piped stdin but only as a single string argument.",
        2: "Accepts structured stdin (JSON, NDJSON) alongside flags.",
        3: "Accepts structured stdin, environment variables, AND config files with priority merging.",
    },
    "deterministic_editing": {
        0: "Modifies state via chat-style interactions or has no idempotent operations.",
        1: "Supports CRUD but requires multi-step state tracking.",
        2: "Idempotent create/replace semantics. Resources are content-addressable.",
        3: "All mutations are idempotent. Full dry-run and rollback support. Outcome preview before execution.",
    },
    "error_defense_in_depth": {
        0: "Errors are terse, sometimes cryptic. No error codes or structured output.",
        1: "English prose errors. Machine-readable exit codes.",
        2: "Structured JSON errors with error codes, exit codes, and user-facing messages.",
        3: "Structured JSON errors in any output mode. Stack traces behind --verbose. Non-zero exit codes for all failures.",
    },
    "stateless_idempotent": {
        0: "Heavy reliance on local state files, environment, or order of operations.",
        1: "Uses state but provides --reset or --force to override.",
        2: "Most operations are stateless. State is explicitly passed or configured.",
        3: "Fully stateless. No hidden state. All configuration is explicit per invocation.",
    },
    "explicit_control_flow": {
        0: "No flags for controlling execution. Runs to completion or fails silently.",
        1: "--dry-run or --yes flags on some commands.",
        2: "Consistent --dry-run, --yes, --no across all mutating commands.",
        3: "--dry-run with structured output preview. Always prompts before destructive actions. CI-mode for unattended use.",
    },
    "tool_discovery": {
        0: "No --help, man pages, or auto-completion. Only README documentation.",
        1: "--help exists but is verbose. No completion or schema.",
        2: "Detailed --help with examples. Shell completion and --json-schema for all commands.",
        3: "--help with examples. Shell completion. OpenAPI/Schema for tool description. MCP/ACP server for agent-native discovery.",
    },
}


def score_cli(cli_name: str, scores: Dict[str, int]) -> Dict[str, Any]:
    """Score a CLI on the Agent DX Scale.

    Args:
        cli_name: Name of the CLI tool
        scores: Dict of axis -> score (0-3) for each of the 7 axes

    Returns:
        Dict with per-axis breakdown, total score, and recommendations
    """
    if not scores:
        scores = {ax: 0 for ax in CLI_SCALE_AXES}

    results = {}
    total = 0
    recommendations = []

    for axis in CLI_SCALE_AXES:
        score = max(0, min(3, scores.get(axis, 0)))
        criteria = CLI_SCALE_CRITERIA[axis]
        description = criteria.get(score, "Unknown score")
        total += score

        results[axis] = {
            "score": score,
            "max": 3,
            "description": description,
            "next_level": criteria.get(score + 1, ""),
        }

        if score < 2:
            recommendations.append(f"Increase '{axis}' from {score}/3 to 2/3: {criteria.get(2, '')}")
        if score == 2:
            recommendations.append(f"Consider advancing '{axis}' to 3/3: {criteria.get(3, '')}")

    total_max = len(CLI_SCALE_AXES) * 3
    pct = total / total_max * 100

    return {
        "cli_name": cli_name,
        "total_score": total,
        "max_score": total_max,
        "percentage": round(pct, 1),
        "per_axis": results,
        "recommendations": recommendations[:5],
        "grade": _cli_grade(pct),
    }


def _cli_grade(pct: float) -> str:
    if pct >= 90: return "A — Agent-native. Designed for AI-first usage."
    if pct >= 75: return "B — Agent-ready. Minor gaps for seamless agent use."
    if pct >= 50: return "C — Agent-tolerable. Works but has friction points."
    if pct >= 25: return "D — Agent-hostile. Requires workarounds."
    return "F — Human-only. Needs fundamental redesign for agent use."


# ═══════════════════════════════════════════════════════════════════════════════
# 3. @json-render/ink — Terminal UI from JSON
# ═══════════════════════════════════════════════════════════════════════════════

INK_COMPONENT_TYPES = [
    "text", "box", "stack", "input", "button",
    "list", "table", "spinner", "progress", "tree",
    "tabs", "panel", "badge", "divider", "link",
]


def render_ink_spec(spec: Dict[str, Any]) -> str:
    """Generate an @json-render/ink terminal UI spec from a JSON component tree.

    Args:
        spec: Component tree with {type, props, children} structure

    Returns:
        TypeScript/JS code string using @json-render/ink API
    """
    comp_type = spec.get("type", "box")
    props = spec.get("props", {})
    children = spec.get("children", [])

    # Import generation
    imports = [
        'import { defineCatalog } from "@json-render/core";',
        'import { schema } from "@json-render/ink/schema";',
        'import { standardComponentDefinitions } from "@json-render/ink/catalog";',
        'import { defineRegistry, Renderer } from "@json-render/ink";',
    ]

    # Component registration
    components = _collect_ink_components(spec)
    comp_defs = {}
    for comp_type_name in components:
        if comp_type_name not in ("text", "box", "stack", "input", "button", "list", "table"):
            comp_defs[comp_type_name] = {
                "props": {"title": "z.string()"},
                "slots": [],
                "description": f"Custom {comp_type_name} component",
            }

    # Generate catalog code
    lines = ["// Auto-generated @json-render/ink spec"]
    lines.extend(imports)
    lines.append("")
    lines.append("const catalog = defineCatalog(schema, {")
    lines.append("  components: {")
    for name, defn in comp_defs.items():
        lines.append(f'    {name}: {{')
        lines.append(f"      props: z.object({{ title: z.string() }}),")
        lines.append(f"      slots: [],")
        lines.append("      description: '" + defn.get("description", "") + "',")
        lines.append(f"    }},")
    lines.append("    ...standardComponentDefinitions,")
    lines.append("  },")
    lines.append("});")
    lines.append("")
    lines.append("const registry = defineRegistry({")
    lines.append("  renderer: Renderer.Textual,")
    lines.append("  catalog,")
    lines.append("});")
    lines.append("")
    lines.append("export { catalog, registry };")

    return "\n".join(lines)


def _collect_ink_components(spec: Dict[str, Any]) -> set:
    """Recursively collect all component types from a spec tree."""
    types = set()
    comp_type = spec.get("type", "box")
    if comp_type:
        types.add(comp_type)
    for child in spec.get("children", []):
        types.update(_collect_ink_components(child))
    return types


# ═══════════════════════════════════════════════════════════════════════════════
# 4. TDD Red-Green-Refactor Workflow
# ═══════════════════════════════════════════════════════════════════════════════

def generate_tdd_cycle(description: str, language: str = "typescript") -> Dict[str, Any]:
    """Generate a TDD cycle structure for a feature.

    Args:
        description: What feature to implement
        language: Target language (typescript, python, etc.)

    Returns:
        Dict with Red, Green, Refactor phase instructions
    """
    sanitized = description.strip().lower().replace(" ", "_")[:40]

    if language == "typescript":
        test_framework = "vitest"
        test_suffix = ".test.ts"
        code_suffix = ".ts"
    elif language == "python":
        test_framework = "pytest"
        test_suffix = "_test.py"
        code_suffix = ".py"
    else:
        test_framework = "vitest"
        test_suffix = ".test.ts"
        code_suffix = ".ts"

    return {
        "feature": description,
        "language": language,
        "framework": test_framework,
        "phases": {
            "red": {
                "title": "RED — Write a failing test first",
                "steps": [
                    f"1. Import the module/function (doesn't exist yet)",
                    f"2. Write the minimal test case for '{sanitized}'",
                    f"3. Run `npx {test_framework} run` — test MUST fail",
                    f"4. Verify failure is about missing implementation, not config",
                ],
                "file": f"{sanitized}{test_suffix}",
                "template": _tdd_test_template(sanitized, language, test_framework),
            },
            "green": {
                "title": "GREEN — Minimal implementation to pass the test",
                "steps": [
                    f"1. Create the minimal implementation for '{sanitized}'",
                    f"2. Write ONLY enough code to pass the test — no more",
                    f"3. Run tests — all MUST pass",
                    "4. Do NOT optimize or refactor yet",
                ],
                "file": f"{sanitized}{code_suffix}",
                "template": _tdd_impl_template(sanitized, language),
            },
            "refactor": {
                "title": "REFACTOR — Clean up while keeping green",
                "steps": [
                    "1. Improve naming, remove duplication, optimize",
                    "2. Run tests after EVERY change — revert if they turn red",
                    "3. Ensure the public API is clean and typed",
                    "4. Document the module with JSDoc/docstrings",
                ],
            },
        },
        "cycle_complete_check": [
            f"✓ Test exists for '{sanitized}'",
            f"✓ Implementation in {sanitized}{code_suffix}",
            "✓ All tests passing",
            "✓ Code is clean and documented",
        ],
    }


def _tdd_test_template(name: str, language: str, framework: str) -> str:
    if language == "typescript":
        return f"""import {{ describe, it, expect }} from "{framework}";
{{% if framework == "vitest" %}}
import {{ {name} }} from "./{name}";

describe("{name}", () => {{
  it("should {name.replace('_', ' ')}", () => {{
    const result = {name}();
    expect(result).toBeDefined();
  }});
}});"""
    elif language == "python":
        return f"""import pytest
from {name} import {name}

def test_{name}():
    \"\"\"Test that {name.replace('_', ' ')} works.\"\"\"
    result = {name}()
    assert result is not None
"""
    return ""


def _tdd_impl_template(name: str, language: str) -> str:
    if language == "typescript":
        return f"""/**
 * TODO: Implement {name.replace('_', ' ')}.
 * This is the minimal implementation to pass the test.
 */
export function {name}(): unknown {{
  // TODO: implement
  throw new Error("Not implemented");
}}"""
    elif language == "python":
        return f"""def {name}():
    \"\"\"TODO: Implement {name.replace('_', ' ')}.\"\"\"
    raise NotImplementedError
"""
    return ""


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Typed Service Contracts (Spec & Handler Pattern)
# ═══════════════════════════════════════════════════════════════════════════════

def generate_service_contract(name: str, operations: List[Dict[str, Any]]) -> str:
    """Generate a Typed Service Contract (Spec & Handler pattern).

    Args:
        name: Service/contract name
        operations: List of {name, input_schema, output_schema, error_types}

    Returns:
        TypeScript code string with spec.ts and handler.ts skeleton
    """
    spec_lines = [
        "// =============================================================================",
        f"// {name} — Typed Service Contract (Spec & Handler Pattern)",
        "// =============================================================================",
        "",
        'import { z } from "zod";',
        "",
        "// ── Input Schema ─────────────────────────────────────────────────────────────",
    ]

    handler_lines = [
        "// =============================================================================",
        f"// {name} — Handler Implementation",
        "// =============================================================================",
        "",
        f'import type {{ {name}Spec }} from "./spec";',
        f'import {{ {name}Errors }} from "./spec";',
        "",
    ]

    for i, op in enumerate(operations):
        op_name = op.get("name", f"operation_{i}")
        input_desc = op.get("input_schema", {})
        output_desc = op.get("output_schema", {})
        error_types = op.get("error_types", ["ValidationError", "NotFoundError"])

        # Spec
        spec_lines.extend([
            "",
            f"// ── {op_name} ────────────────────────────────────────────────────────────",
            f"export const {op_name}InputSchema = z.object({{",
        ])
        for field_name, field_type in input_desc.items():
            spec_lines.append(f"  {field_name}: z.{field_type}(),")
        spec_lines.extend([
            "});",
            "",
            f"export type {op_name}Input = z.infer<typeof {op_name}InputSchema>;",
            "",
            f"export type {op_name}Output = {{",
        ])
        for field_name, field_type in output_desc.items():
            spec_lines.append(f"  {field_name}: {field_type};")
        spec_lines.extend([
            "};",
            "",
            f"export type {op_name}Errors = " +
            " | ".join(f'{{ kind: "{e}"; message: string }}' for e in error_types) + ";",
            "",
            f"export type {op_name}Result = " +
            " | ".join([
                f'{{ success: true; data: {op_name}Output }}',
                f'{{ success: false; error: {op_name}Errors }}',
            ]) + ";",
            "",
            f"export interface I{op_name[0].upper() + op_name[1:]}Spec {{",
            f"  execute(input: {op_name}Input): Promise<{op_name}Result>;",
            "}",
        ])

        # Handler
        handler_lines.extend([
            "",
            f"// ── {op_name} Handler ────────────────────────────────────────────────────",
            f"export class {op_name[0].upper() + op_name[1:]}Handler implements I{op_name[0].upper() + op_name[1:]}Spec {{",
            "",
            f"  async execute(input: {op_name}Input): Promise<{op_name}Result> {{",
            "    try {",
            f"      const parsed = {op_name}InputSchema.parse(input);",
            "      // TODO: implement",
            f"      return {{ success: true, data: parsed as unknown as {op_name}Output }};",
            "    } catch (error) {",
            '      return { success: false, error: { kind: "ValidationError", message: String(error) } };',
            "    }",
            "  }",
            "}",
        ])

    return "\n".join(spec_lines) + "\n\n// =============================================================================\n\n" + "\n".join(handler_lines)


# ═══════════════════════════════════════════════════════════════════════════════
# Tool Registration
# ═══════════════════════════════════════════════════════════════════════════════

def register_all_tools():
    """Register all google-labs tools with the Pravidhi registry."""
    registry = get_registry()

    # 1. DESIGN.md linter
    def handle_design_lint(params):
        content = params.get("content", "")
        if params.get("file"):
            content = Path(params["file"]).read_text()
        result = lint_design_md(content)
        return json.dumps(result, indent=2)

    registry.register_tool(
        name="design_lint",
        description="Lint a DESIGN.md file against the design.md spec. Catches broken token refs, missing tokens, WCAG contrast issues, and orphaned tokens.",
        schema={
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "DESIGN.md content to lint"},
                "file": {"type": "string", "description": "Path to DESIGN.md file (alternative to content)"},
            },
        },
        handler=handle_design_lint,
        toolset="design",
        source="google-labs",
    )

    # 2. DESIGN.md diff
    def handle_design_diff(params):
        before = params.get("before", "")
        after = params.get("after", "")
        if params.get("before_file"):
            before = Path(params["before_file"]).read_text()
        if params.get("after_file"):
            after = Path(params["after_file"]).read_text()
        result = diff_design_md(before, after)
        return json.dumps(result, indent=2)

    registry.register_tool(
        name="design_diff",
        description="Compare two DESIGN.md files and detect token-level changes, additions, removals, and regressions.",
        schema={
            "type": "object",
            "properties": {
                "before": {"type": "string", "description": "Before DESIGN.md content"},
                "after": {"type": "string", "description": "After DESIGN.md content"},
                "before_file": {"type": "string"},
                "after_file": {"type": "string"},
            },
            "required": [],
        },
        handler=handle_design_diff,
        toolset="design",
        source="google-labs",
    )

    # 3. DESIGN.md export
    def handle_design_export(params):
        content = params.get("content", "")
        fmt = params.get("format", "json-tailwind")
        if params.get("file"):
            content = Path(params["file"]).read_text()
        result = export_design_md(content, fmt)
        return result if result else json.dumps({"error": f"Unknown format: {fmt}"})

    registry.register_tool(
        name="design_export",
        description="Export DESIGN.md tokens to other formats: json-tailwind, css-tailwind, dtcg.",
        schema={
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "DESIGN.md content"},
                "file": {"type": "string", "description": "Path to DESIGN.md file"},
                "format": {
                    "type": "string",
                    "enum": ["json-tailwind", "css-tailwind", "dtcg"],
                    "description": "Export format",
                },
            },
            "required": ["format"],
        },
        handler=handle_design_export,
        toolset="design",
        source="google-labs",
    )

    # 4. DESIGN.md spec (output the spec summary)
    registry.register_tool(
        name="design_spec",
        description="Output the DESIGN.md format specification summary — token schema, section order, component properties.",
        schema={
            "type": "object",
            "properties": {
                "include_rules": {"type": "boolean", "description": "Include linting rules table"},
            },
        },
        handler=lambda params: json.dumps({
            "format": "DESIGN.md (alpha)",
            "schema": {
                "required_top_level": ["colors"],
                "optional_top_level": ["version", "name", "description", "typography", "rounded", "spacing", "components"],
                "section_order": ["Overview", "Colors", "Typography", "Layout & Spacing", "Elevation & Depth", "Shapes", "Components", "Do's and Don'ts"],
            },
            "component_properties": ["backgroundColor", "textColor", "typography", "rounded", "padding", "size", "height", "width"],
            "lint_rules": DESIGN_MD_LINT_RULES,
        }, indent=2),
        toolset="design",
        source="google-labs",
    )

    # 5. Agent DX CLI Scale
    def handle_cli_scale(params):
        cli_name = params.get("cli_name", "unknown-cli")
        scores = params.get("scores", {})
        result = score_cli(cli_name, scores)
        return json.dumps(result, indent=2)

    registry.register_tool(
        name="cli_scale_score",
        description="Score a CLI on the Agent DX Scale (0-21). Evaluates 7 axes: machine-readable output, raw payload input, deterministic editing, error defense-in-depth, stateless idempotence, explicit control flow, and tool discovery.",
        schema={
            "type": "object",
            "properties": {
                "cli_name": {"type": "string", "description": "Name of the CLI tool to evaluate"},
                "scores": {
                    "type": "object",
                    "description": "Dict mapping axis names to scores 0-3. Axes: machine_readable_output, raw_payload_input, deterministic_editing, error_defense_in_depth, stateless_idempotent, explicit_control_flow, tool_discovery",
                    "additionalProperties": {"type": "integer", "minimum": 0, "maximum": 3},
                },
            },
            "required": ["cli_name"],
        },
        handler=handle_cli_scale,
        toolset="dx",
        source="google-labs",
    )

    # 6. @json-render/ink spec generator
    def handle_ink_render(params):
        spec = params.get("spec", {})
        if isinstance(spec, str):
            spec = json.loads(spec)
        result = render_ink_spec(spec)
        return result

    registry.register_tool(
        name="json_render_ink",
        description="Generate an @json-render/ink terminal UI specification from a JSON component tree. Produces TypeScript code using the defineCatalog + defineRegistry API.",
        schema={
            "type": "object",
            "properties": {
                "spec": {
                    "type": "object",
                    "description": "Component tree with {type, props, children}. Example: {'type': 'box', 'props': {'title': 'App'}, 'children': [{'type': 'text', 'props': {'content': 'Hello'}}]}",
                },
            },
            "required": ["spec"],
        },
        handler=handle_ink_render,
        toolset="ui",
        source="google-labs",
    )

    # 7. TDD cycle generator
    def handle_tdd_cycle(params):
        description = params.get("description", "")
        language = params.get("language", "typescript")
        result = generate_tdd_cycle(description, language)
        return json.dumps(result, indent=2)

    registry.register_tool(
        name="tdd_workflow",
        description="Generate a complete TDD Red-Green-Refactor cycle for a feature. Creates test template, implementation template, and validation checklist.",
        schema={
            "type": "object",
            "properties": {
                "description": {"type": "string", "description": "Feature description"},
                "language": {"type": "string", "enum": ["typescript", "python"], "description": "Target language"},
            },
            "required": ["description"],
        },
        handler=handle_tdd_cycle,
        toolset="development",
        source="google-labs",
    )

    # 8. Typed Service Contract generator
    def handle_service_contract(params):
        name = params.get("name", "Service")
        operations = params.get("operations", [])
        result = generate_service_contract(name, operations)
        return result

    registry.register_tool(
        name="typed_service_contract",
        description="Generate a Typed Service Contract using the Spec & Handler pattern. Creates Zod-validated input/output schemas with discriminated union result types.",
        schema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Service/contract name"},
                "operations": {
                    "type": "array",
                    "description": "Operations to include. Each: {name, input_schema: {field: type}, output_schema: {field: type}, error_types: [str]}",
                    "items": {"type": "object"},
                },
            },
            "required": ["name"],
        },
        handler=handle_service_contract,
        toolset="development",
        source="google-labs",
    )

    logger.info(f"Registered {8} google-labs tools in Pravidhi registry")


# Auto-register on import
register_all_tools()
