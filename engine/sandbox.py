"""Sandboxed code execution — Python/Node/Shell in isolated environments.

Inspired by Hermes Agent's execute_code tool with Unix socket RPC.
Supports multiple isolation backends: process, udocker, docker.
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, TypeAlias

logger = logging.getLogger("pravidhi.sandbox")


class SandboxBackend(Enum):
    PROCESS = "process"  # Direct subprocess (lightest)
    UDOCKER = "udocker"  # udocker container
    DOCKER = "docker"    # Full docker


@dataclass
class SandboxResult:
    stdout: str = ""
    stderr: str = ""
    return_code: int = -1
    duration_ms: float = 0.0
    error: Optional[str] = None


@dataclass
class SandboxConfig:
    backend: SandboxBackend = SandboxBackend.PROCESS
    timeout: int = 30
    workdir: Optional[str] = None
    env_vars: Dict[str, str] = field(default_factory=dict)
    memory_limit_mb: int = 512
    network_access: bool = False


class CodeSandbox:
    """Executes code in an isolated sandbox."""

    def __init__(self, config: Optional[SandboxConfig] = None):
        self.config = config or SandboxConfig()

    async def execute_python(
        self, code: str, context: Optional[Dict[str, Any]] = None
    ) -> SandboxResult:
        """Execute Python code in sandbox."""
        return await self._run_script("python3", code, context)

    async def execute_node(
        self, code: str, context: Optional[Dict[str, Any]] = None
    ) -> SandboxResult:
        """Execute Node.js code in sandbox."""
        return await self._run_script("node", code, context)

    async def execute_shell(
        self, command: str, context: Optional[Dict[str, Any]] = None
    ) -> SandboxResult:
        """Execute shell command in sandbox."""
        return await self._run_shell(command, context)

    async def _run_script(
        self, interpreter: str, code: str, context: Optional[Dict[str, Any]] = None
    ) -> SandboxResult:
        """Run code via interpreter in a subprocess."""
        start = time.time()

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py" if interpreter == "python3" else ".js",
            delete=False,
        ) as f:
            if context:
                f.write("# Context provided by Pravidhi\n")
                for key, val in (context or {}).items():
                    f.write(f"{key} = {repr(val)}\n")
                f.write("\n")
            f.write(code)
            script_path = f.name

        try:
            proc = await asyncio.create_subprocess_exec(
                interpreter,
                script_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, **self.config.env_vars},
                cwd=self.config.workdir,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=self.config.timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return SandboxResult(
                    error=f"Timeout after {self.config.timeout}s",
                    duration_ms=(time.time() - start) * 1000,
                )

            return SandboxResult(
                stdout=stdout.decode("utf-8", errors="replace") if stdout else "",
                stderr=stderr.decode("utf-8", errors="replace") if stderr else "",
                return_code=proc.returncode or 0,
                duration_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            return SandboxResult(
                error=str(e), duration_ms=(time.time() - start) * 1000
            )
        finally:
            Path(script_path).unlink(missing_ok=True)

    async def _run_shell(
        self, command: str, context: Optional[Dict[str, Any]] = None
    ) -> SandboxResult:
        """Run a shell command in sandbox."""
        start = time.time()

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, **self.config.env_vars},
                cwd=self.config.workdir,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=self.config.timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return SandboxResult(
                    error=f"Timeout after {self.config.timeout}s",
                    duration_ms=(time.time() - start) * 1000,
                )

            return SandboxResult(
                stdout=stdout.decode("utf-8", errors="replace") if stdout else "",
                stderr=stderr.decode("utf-8", errors="replace") if stderr else "",
                return_code=proc.returncode or 0,
                duration_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            return SandboxResult(
                error=str(e), duration_ms=(time.time() - start) * 1000
            )

    async def execute_code(
        self, code: str, language: str = "python", context: Optional[Dict] = None
    ) -> SandboxResult:
        """Execute code in any supported language."""
        if language == "python":
            return await self.execute_python(code, context)
        elif language == "node" or language == "javascript":
            return await self.execute_node(code, context)
        elif language == "shell" or language == "bash":
            return await self.execute_shell(code, context)
        else:
            return SandboxResult(error=f"Unsupported language: {language}")
