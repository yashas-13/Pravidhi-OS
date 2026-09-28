"""Pravidhi Reverse Engineering Engine.

Binary analysis via Ghidra (PyGhidra/JPype), symbolic execution (z3-solver),
and LLM-assisted decompilation (Claude + GPT-4o).

Supports PE, ELF, Mach-O, raw firmware, .NET assemblies, and Java classes.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import struct
import subprocess
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, TypeAlias, Union
import math


logger = logging.getLogger("pravidhi.reverse_engineering")


# ── Types ─────────────────────────────────────────────────────────────────────

class BinaryFormat(Enum):
    PE = "pe"
    ELF = "elf"
    MACHO = "macho"
    RAW = "raw"
    DOTNET = "dotnet"
    JAVA_CLASS = "java_class"
    UNKNOWN = "unknown"


@dataclass
class BinaryInfo:
    path: str
    format: BinaryFormat = BinaryFormat.UNKNOWN
    arch: str = ""
    size: int = 0
    entropy: float = 0.0
    sections: List[Dict[str, Any]] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)
    exports: List[str] = field(default_factory=list)
    strings: List[Dict[str, Any]] = field(default_factory=list)
    hashes: Dict[str, str] = field(default_factory=dict)


@dataclass
class AnalysisReport:
    binary: BinaryInfo
    functions: List[Dict[str, Any]] = field(default_factory=list)
    vulnerabilities: List[Dict[str, Any]] = field(default_factory=list)
    decompiled: Dict[str, str] = field(default_factory=dict)
    call_graph: Dict[str, List[str]] = field(default_factory=dict)
    llm_insights: Dict[str, Any] = field(default_factory=dict)
    summary: str = ""


# ── Format Detection ──────────────────────────────────────────────────────────

def detect_format(path: str) -> BinaryFormat:
    """Detect binary format using magic bytes and heuristics."""
    try:
        with open(path, "rb") as f:
            header = f.read(16)
    except Exception:
        return BinaryFormat.UNKNOWN

    # PE (Windows)
    if header[:2] == b"MZ":
        return BinaryFormat.PE

    # ELF (Linux)
    if header[:4] == b"\x7fELF":
        return BinaryFormat.ELF

    # Mach-O (macOS)
    if header[:4] in (b"\xfe\xed\xfa\xce", b"\xce\xfa\xed\xfe",
                      b"\xfe\xed\xfa\xcf", b"\xcf\xfa\xed\xfe",
                      b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca"):
        return BinaryFormat.MACHO

    # Java class
    if header[:4] == b"\xca\xfe\xba\xbe":
        return BinaryFormat.JAVA_CLASS

    # .NET (starts with MZ but has PE signature at 0x3C offset)
    if header[:2] == b"MZ":
        try:
            pe_offset = struct.unpack_from("<I", header, 0x3C)[0]
            with open(path, "rb") as f:
                f.seek(pe_offset)
                if f.read(4) == b"PE\x00\x00":
                    return BinaryFormat.DOTNET
        except Exception:
            pass

    # Check for known firmware headers
    if header[:4] in (b"BPaC", b"UHDR", b"TRX\x00", b"CRC\x00"):
        return BinaryFormat.RAW

    # Fallback: check with 'file' command
    if shutil.which("file"):
        try:
            result = subprocess.run(
                ["file", path], capture_output=True, text=True, timeout=5
            )
            output = result.stdout.lower()
            if "elf" in output:
                return BinaryFormat.ELF
            if "pe32" in output or "pe32+" in output or "dll" in output:
                return BinaryFormat.PE
            if "mach-o" in output or "mach object" in output:
                return BinaryFormat.MACHO
            if "java class" in output:
                return BinaryFormat.JAVA_CLASS
            if ".net" in output:
                return BinaryFormat.DOTNET
        except Exception:
            pass

    return BinaryFormat.UNKNOWN


# ── Binary Info Extraction ────────────────────────────────────────────────────

def compute_entropy(data: bytes) -> float:
    """Compute Shannon entropy of binary data."""
    if not data:
        return 0.0
    entropy = 0.0
    for x in range(256):
        p_x = data.count(x) / len(data)
        if p_x > 0:
            entropy += -p_x * math.log2(p_x)
    return entropy


def extract_strings(path: str, min_length: int = 4) -> List[Dict[str, Any]]:
    """Extract ASCII and Unicode strings from binary."""
    result = []
    try:
        with open(path, "rb") as f:
            data = f.read()

        # ASCII strings
        current = b""
        for i, byte in enumerate(data):
            if 32 <= byte <= 126:
                current += bytes([byte])
            else:
                if len(current) >= min_length:
                    try:
                        result.append({
                            "offset": i - len(current),
                            "value": current.decode("ascii", errors="replace"),
                            "length": len(current),
                        })
                    except Exception:
                        pass
                current = b""

        # Unicode strings (UTF-16LE)
        current = b""
        for i in range(0, len(data) - 1, 2):
            if data[i] != 0 and data[i + 1] == 0:
                current += bytes([data[i]])
            else:
                if len(current) >= min_length:
                    try:
                        result.append({
                            "offset": i - len(current) * 2,
                            "value": current.decode("utf-8", errors="replace"),
                            "length": len(current),
                        })
                    except Exception:
                        pass
                current = b""

    except Exception as e:
        logger.warning(f"String extraction failed: {e}")

    return result


def compute_hashes(path: str) -> Dict[str, str]:
    """Compute MD5, SHA1, SHA256 hashes."""
    import hashlib
    hashes = {}
    try:
        with open(path, "rb") as f:
            data = f.read()
        hashes["md5"] = hashlib.md5(data).hexdigest()
        hashes["sha1"] = hashlib.sha1(data).hexdigest()
        hashes["sha256"] = hashlib.sha256(data).hexdigest()
    except Exception as e:
        logger.warning(f"Hashing failed: {e}")
    return hashes


# ── Ghidra Integration (PyGhidra) ─────────────────────────────────────────────

def _check_pyghidra() -> bool:
    """Check if PyGhidra is available."""
    try:
        import pyghidra  # noqa: F401
        return True
    except ImportError:
        return False


async def analyze_with_ghidra(path: str, timeout: int = 300) -> Dict[str, Any]:
    """Analyze binary using Ghidra via PyGhidra (in-process)."""
    if not _check_pyghidra():
        return {"error": "PyGhidra not installed. Run: pip install pyghidra"}

    try:
        from pyghidra import GhidraPlugin  # type: ignore
        from ghidra.program.model.listing import Function  # type: ignore
        from ghidra.program.model.symbol import SymbolType  # type: ignore

        result: Dict[str, Any] = {
            "functions": [],
            "strings": [],
            "imports": [],
            "exports": [],
            "call_graph": {},
        }

        # Start Ghidra headless
        with GhidraPlugin() as plugin:
            plugin.open_program(path)

            # Extract functions
            fm = plugin.get_current_program().getFunctionManager()
            for func in fm.getFunctions(True):
                body = func.getBody()
                if body:
                    result["functions"].append({
                        "name": func.getName(),
                        "address": str(func.getEntryPoint()),
                        "size": body.getNumAddresses(),
                        "calling_convention": func.getCallingConvention() or "unknown",
                    })

            # Extract strings
            listing = plugin.get_current_program().getListing()
            data_iter = listing.getDefinedData(True)
            while data_iter.hasNext():
                data = data_iter.next()
                if data.isString():
                    result["strings"].append({
                        "address": str(data.getAddress()),
                        "value": str(data.getValue()),
                    })

            # Extract imports/exports
            sym_table = plugin.get_current_program().getSymbolTable()
            for sym in sym_table.getAllSymbols(True):
                if sym.getSymbolType() == SymbolType.FUNCTION:
                    if sym.isExternal():
                        result["imports"].append(sym.getName())
                    else:
                        result["exports"].append(sym.getName())

        return result

    except Exception as e:
        logger.error(f"Ghidra analysis failed: {e}")
        return {"error": str(e)}


# ── Symbolic Execution (z3-solver) ────────────────────────────────────────────

def _check_z3() -> bool:
    try:
        import z3  # noqa: F401
        return True
    except ImportError:
        return False


class SymbolicExecutor:
    """Symbolic execution engine using z3-solver."""

    def __init__(self):
        self._check_deps()

    def _check_deps(self):
        if not _check_z3():
            raise ImportError("z3-solver not installed. Run: pip install z3-solver")

    def solve_constraints(
        self, constraints: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Solve a set of constraints symbolically.

        Args:
            constraints: List of constraint dicts with:
                - 'type': 'eq' | 'neq' | 'lt' | 'gt' | 'range' | 'and' | 'or'
                - 'var': variable name
                - 'val': value (int, or [min, max] for range)
                - 'vars': [var names] for 'and'/'or' multi-var
                - 'vals': [values] for 'and'/'or'

        Returns:
            Dict with 'sat' (bool) and 'model' (dict of var->value)
        """
        import z3

        solver = z3.Solver()
        var_map: Dict[str, z3.BitVec] = {}

        # Collect all variables
        for c in constraints:
            if "var" in c and c["var"] not in var_map:
                var_map[c["var"]] = z3.BitVec(c["var"], 64)
            if "vars" in c:
                for v in c["vars"]:
                    if v not in var_map:
                        var_map[v] = z3.BitVec(v, 64)

        # Add constraints
        for c in constraints:
            t = c.get("type", "eq")
            if t == "eq" and "var" in c and "val" in c:
                solver.add(var_map[c["var"]] == c["val"])
            elif t == "neq" and "var" in c and "val" in c:
                solver.add(var_map[c["var"]] != c["val"])
            elif t == "lt" and "var" in c and "val" in c:
                solver.add(var_map[c["var"]] < c["val"])
            elif t == "gt" and "var" in c and "val" in c:
                solver.add(var_map[c["var"]] > c["val"])
            elif t == "range" and "var" in c and "val" in c:
                solver.add(z3.And(var_map[c["var"]] >= c["val"][0],
                                  var_map[c["var"]] <= c["val"][1]))
            elif t == "and" and "vars" in c and "vals" in c:
                solver.add(z3.And([var_map[v] == val
                                   for v, val in zip(c["vars"], c["vals"])]))

        result = solver.check()
        if result == z3.sat:
            model = solver.model()
            return {
                "sat": True,
                "model": {
                    str(d): model[d].as_long() if model[d] is not None else 0
                    for d in model.decls()
                },
            }
        return {"sat": False, "model": {}}

    def analyze_buffer_overflow(
        self, buffer_size: int, offset: int, access_size: int
    ) -> Dict[str, Any]:
        """Check if a memory access can overflow a buffer."""
        import z3

        solver = z3.Solver()
        offset_var = z3.BitVec("offset", 64)
        solver.add(offset_var == offset)
        solver.add(z3.Or(offset_var < 0, offset_var + access_size > buffer_size))

        result = solver.check()
        if result == z3.sat:
            model = solver.model()
            return {
                "vulnerable": True,
                "type": "buffer_overflow",
                "buffer_size": buffer_size,
                "access_end": offset + access_size,
                "overflow_by": max(0, offset + access_size - buffer_size),
            }
        return {"vulnerable": False, "type": "safe", "buffer_size": buffer_size}


# ── LLM-Assisted Decompilation ────────────────────────────────────────────────

class DecompilerAssistant:
    """LLM-assisted decompilation using Claude (Anthropic) and GPT-4o (OpenAI)."""

    def __init__(self):
        self.anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
        self.openai_key = os.getenv("OPENAI_API_KEY", "")

    async def explain_function(
        self, decompiled_code: str, language: str = "c",
        provider: str = "auto",
    ) -> Dict[str, Any]:
        """Explain a decompiled function using LLM."""
        if provider == "auto":
            provider = "anthropic" if self.anthropic_key else "openai"

        prompt = f"""You are an expert reverse engineer. Analyze this {language} decompiled code:

```{language}
{decompiled_code[:6000]}
```

Provide:
1. **Purpose**: What this function does (1-2 sentences)
2. **Logic**: Step-by-step explanation
3. **Vulnerabilities**: Any security issues you spot
4. **Renamed**: Suggest better variable/function names
5. **Pseudocode**: Simplified pseudocode version
"""

        if provider == "anthropic":
            return await self._call_anthropic(prompt)
        else:
            return await self._call_openai(prompt)

    async def decompile_pseudocode(
        self, assembly: str, arch: str = "x64",
    ) -> Dict[str, Any]:
        """Convert assembly to high-level pseudocode using LLM."""
        prompt = f"""You are an expert reverse engineer. Convert this {arch} assembly to high-level C pseudocode:

```asm
{assembly[:4000]}
```

Provide:
1. The decompiled C pseudocode
2. An explanation of what the function does
3. Identify any interesting patterns (anti-debug, obfuscation, crypto, etc.)
"""

        provider = "anthropic" if self.anthropic_key else "openai"
        if provider == "anthropic":
            return await self._call_anthropic(prompt)
        return await self._call_openai(prompt)

    async def _call_anthropic(self, prompt: str) -> Dict[str, Any]:
        try:
            import anthropic
            client = anthropic.AsyncAnthropic(api_key=self.anthropic_key)
            response = await client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}],
            )
            return {
                "provider": "anthropic",
                "model": "claude-sonnet-4",
                "content": response.content[0].text,
                "usage": {"input_tokens": response.usage.input_tokens,
                          "output_tokens": response.usage.output_tokens},
            }
        except Exception as e:
            logger.error(f"Anthropic call failed: {e}")
            return {"provider": "anthropic", "error": str(e)}

    async def _call_openai(self, prompt: str) -> Dict[str, Any]:
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=self.openai_key)
            response = await client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=4096,
                temperature=0.3,
            )
            return {
                "provider": "openai",
                "model": "gpt-4o",
                "content": response.choices[0].message.content,
                "usage": {"input_tokens": response.usage.prompt_tokens,
                          "output_tokens": response.usage.completion_tokens},
            }
        except Exception as e:
            logger.error(f"OpenAI call failed: {e}")
            return {"provider": "openai", "error": str(e)}


# ── Main Analyzer ─────────────────────────────────────────────────────────────

class BinaryAnalyzer:
    """Main binary analysis orchestrator."""

    def __init__(self, use_ghidra: bool = True, use_z3: bool = True,
                 use_llm: bool = True):
        self.use_ghidra = use_ghidra
        self.use_z3 = use_z3
        self.use_llm = use_llm
        self.decompiler = DecompilerAssistant()
        self.symbolic = None
        if use_z3 and _check_z3():
            self.symbolic = SymbolicExecutor()

    async def analyze(self, path: str, depth: str = "basic") -> AnalysisReport:
        """Run full analysis pipeline on a binary."""
        path = os.path.expanduser(path)
        if not os.path.exists(path):
            raise FileNotFoundError(f"Binary not found: {path}")

        size = os.path.getsize(path)
        with open(path, "rb") as f:
            data = f.read()

        fmt = detect_format(path)
        info = BinaryInfo(
            path=path,
            format=fmt,
            arch=self._detect_arch(data, fmt),
            size=size,
            entropy=compute_entropy(data),
            strings=extract_strings(path),
            hashes=compute_hashes(path),
        )

        report = AnalysisReport(binary=info)

        if depth in ("basic", "full"):
            # Basic analysis
            pass

        if depth in ("deep", "full"):
            # Ghidra analysis
            if self.use_ghidra and _check_pyghidra():
                ghidra_result = await analyze_with_ghidra(path)
                if "error" not in ghidra_result:
                    report.functions = ghidra_result.get("functions", [])

            # z3 analysis for vulnerable patterns
            if self.symbolic:
                for s in info.strings:
                    if "password" in s["value"].lower() or "key" in s["value"].lower():
                        report.vulnerabilities.append({
                            "type": "hardcoded_secret",
                            "severity": "high",
                            "description": f"Potential secret at offset {s['offset']}",
                            "value": s["value"],
                        })

            # LLM insights on a few key functions
            if self.use_llm and report.functions:
                key_func = report.functions[0]
                if key_func.get("name") != "unknown":
                    insight = await self.decompiler.explain_function(
                        f"Function: {key_func['name']} at {key_func.get('address', '?')}\n"
                        f"Size: {key_func.get('size', '?')} instructions",
                        language="pseudocode",
                    )
                    report.llm_insights["key_function"] = insight

        # Generate summary
        report.summary = (
            f"Binary: {os.path.basename(path)} ({fmt.value})\n"
            f"Size: {size:,} bytes | Entropy: {info.entropy:.2f}\n"
            f"Functions: {len(report.functions)} | "
            f"Strings: {len(info.strings)} | "
            f"Vulnerabilities: {len(report.vulnerabilities)}"
        )

        return report

    def _detect_arch(self, data: bytes, fmt: BinaryFormat) -> str:
        """Detect architecture from binary headers."""
        if fmt == BinaryFormat.ELF and len(data) >= 20:
            ei_class = data[4]  # 1=32-bit, 2=64-bit
            ei_data = data[5]   # 1=little, 2=big
            e_machine = struct.unpack_from("<H", data, 18)[0] if ei_data == 1 else struct.unpack_from(">H", data, 18)[0]
            arch_map = {
                0: "none", 3: "i386", 8: "mips", 20: "ppc",
                40: "arm", 43: "sparc", 50: "ia64", 62: "x86_64",
                183: "aarch64", 243: "riscv",
            }
            return arch_map.get(e_machine, f"unknown({e_machine})")
        elif fmt == BinaryFormat.PE:
            if len(data) >= 0x100:
                pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
                if pe_offset + 4 <= len(data):
                    machine = struct.unpack_from("<H", data, pe_offset + 4)[0]
                    pe_arch = {0x14c: "i386", 0x8664: "x86_64",
                               0x1c4: "arm", 0xaa64: "aarch64"}
                    return pe_arch.get(machine, f"unknown({hex(machine)})")
        return "unknown"


# ── Tool Registration ─────────────────────────────────────────────────────────

def register_tools():
    """Register reverse engineering tools in Pravidhi registry."""
    from engine.registry import get_registry
    registry = get_registry()

    # Binary analysis tool
    async def handle_analyze(params):
        path = params.get("path", "")
        depth = params.get("depth", "basic")
        analyzer = BinaryAnalyzer()
        report = await analyzer.analyze(path, depth)
        return json.dumps({
            "binary": {
                "path": report.binary.path,
                "format": report.binary.format.value,
                "arch": report.binary.arch,
                "size": report.binary.size,
                "entropy": report.binary.entropy,
                "strings_count": len(report.binary.strings),
                "hashes": report.binary.hashes,
            },
            "functions": len(report.functions),
            "vulnerabilities": report.vulnerabilities,
            "summary": report.summary,
        }, indent=2)

    registry.register_tool(
        name="binary_analyze",
        description="Analyze a binary file (PE, ELF, Mach-O, firmware, .NET, Java). Returns format, architecture, strings, hashes, vulnerabilities.",
        schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to binary file"},
                "depth": {"type": "string", "enum": ["basic", "deep", "full"],
                          "description": "Analysis depth"},
            },
            "required": ["path"],
        },
        handler=handle_analyze,
        toolset="reverse-engineering",
        source="builtin",
    )

    # Symbolic execution tool
    def handle_symbolic(params):
        constraints = params.get("constraints", [])
        executor = SymbolicExecutor()
        result = executor.solve_constraints(constraints)
        return json.dumps(result, indent=2)

    registry.register_tool(
        name="symbolic_execute",
        description="Solve symbolic constraints using z3-solver for vulnerability analysis.",
        schema={
            "type": "object",
            "properties": {
                "constraints": {
                    "type": "array",
                    "description": "List of constraint dicts with type, var, val",
                    "items": {"type": "object"},
                },
            },
            "required": ["constraints"],
        },
        handler=handle_symbolic,
        toolset="reverse-engineering",
        source="builtin",
    )

    # Buffer overflow checker
    def handle_buffer_overflow(params):
        buffer_size = params.get("buffer_size", 0)
        offset = params.get("offset", 0)
        access_size = params.get("access_size", 4)
        executor = SymbolicExecutor()
        result = executor.analyze_buffer_overflow(buffer_size, offset, access_size)
        return json.dumps(result, indent=2)

    registry.register_tool(
        name="check_buffer_overflow",
        description="Use z3 to check if a memory access can overflow a buffer.",
        schema={
            "type": "object",
            "properties": {
                "buffer_size": {"type": "integer", "description": "Size of buffer"},
                "offset": {"type": "integer", "description": "Access offset"},
                "access_size": {"type": "integer", "description": "Size of access in bytes"},
            },
            "required": ["buffer_size", "offset"],
        },
        handler=handle_buffer_overflow,
        toolset="reverse-engineering",
        source="builtin",
    )

    # LLM decompilation assistant
    async def handle_decompile(params):
        code = params.get("code", "")
        language = params.get("language", "c")
        assistant = DecompilerAssistant()
        result = await assistant.explain_function(code, language)
        return json.dumps(result, indent=2)

    registry.register_tool(
        name="llm_decompile",
        description="Use LLM (Claude/GPT-4o) to explain and decompile code.",
        schema={
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Decompiled code to analyze"},
                "language": {"type": "string", "description": "Language (c, python, asm)"},
            },
            "required": ["code"],
        },
        handler=handle_decompile,
        toolset="reverse-engineering",
        source="builtin",
    )

    logger.info("Registered reverse engineering tools")


# Auto-register
register_tools()
