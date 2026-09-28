"""Pravidhi Doctor — system diagnostics, dependency repair, and auto-setup.

Commands:
    pravidhi doctor         — Full system diagnostics
    pravidhi doctor --fix   — Auto-repair all issues
    pravidhi doctor --deps  — Install missing dependencies
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("pravidhi.doctor")


# ── Detect environment ───────────────────────────────────────────────────────

@dataclass
class SystemInfo:
    os: str = ""               # linux, darwin, windows, termux
    os_version: str = ""
    arch: str = ""
    python_version: str = ""
    python_path: str = ""
    is_termux: bool = False
    is_container: bool = False
    is_root: bool = False
    has_systemd: bool = False
    package_manager: str = ""  # apt, pacman, apk, brew, termux-pkg
    shell: str = ""
    home: str = ""
    pravidhi_home: str = ""


def detect_system() -> SystemInfo:
    info = SystemInfo()

    # OS detection
    raw_os = platform.system().lower()
    info.arch = platform.machine()
    info.python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    info.python_path = sys.executable
    info.home = str(Path.home())
    info.pravidhi_home = str(Path.home() / ".pravidhi")
    info.is_root = os.geteuid() == 0 if hasattr(os, "geteuid") else False
    info.shell = os.environ.get("SHELL", "")

    if raw_os == "linux":
        # Termux detection
        if "com.termux" in os.environ.get("HOME", "") or os.path.exists("/data/data/com.termux"):
            info.os = "termux"
            info.is_termux = True
            info.package_manager = "pkg"
        else:
            info.os = "linux"
            # Detect package manager
            for pm, cmd in [("apt", "apt-get"), ("apk", "apk"), ("pacman", "pacman"), ("dnf", "dnf"), ("yum", "yum")]:
                if shutil.which(cmd):
                    info.package_manager = pm
                    break
            # Systemd
            info.has_systemd = shutil.which("systemctl") is not None

        # OS version
        try:
            with open("/etc/os-release") as f:
                for line in f:
                    if line.startswith("PRETTY_NAME="):
                        info.os_version = line.split("=", 1)[1].strip().strip('"')
                        break
        except FileNotFoundError:
            pass

    elif raw_os == "darwin":
        info.os = "darwin"
        info.package_manager = "brew"
    elif raw_os == "windows":
        info.os = "windows"
        info.package_manager = "winget" if shutil.which("winget") else "choco"

    # Container check
    if os.path.exists("/.dockerenv") or os.path.exists("/run/.containerenv"):
        info.is_container = True

    return info


# ── Check definitions ─────────────────────────────────────────────────────────

@dataclass
class CheckResult:
    name: str
    passed: bool
    severity: str = "info"  # error | warning | info
    message: str = ""
    fix_command: str = ""
    details: str = ""


CHECKS: List[Dict[str, Any]] = []


def check(name: str, severity: str = "error"):
    """Decorator to register a diagnostic check."""
    def decorator(fn):
        CHECKS.append({"name": name, "severity": severity, "fn": fn})
        return fn
    return decorator


# ── Checks ─────────────────────────────────────────────────────────────────────

@check("Python version", "error")
def check_python(info: SystemInfo) -> CheckResult:
    major, minor = sys.version_info.major, sys.version_info.minor
    ok = (major == 3 and minor >= 10)
    return CheckResult(
        name="Python version",
        passed=ok,
        severity="error",
        message=f"Python {info.python_version} ({'OK' if ok else 'need 3.10+'})",
        fix_command="Install Python 3.10+: https://python.org/downloads",
    )


@check("Pravidhi package", "error")
def check_pravidhi_pkg(info: SystemInfo) -> CheckResult:
    try:
        import pravidhi  # noqa: F401
        return CheckResult(name="Pravidhi package", passed=True, message="pravidhi package importable")
    except ImportError:
        # Check if we're in the source directory
        cwd = Path.cwd()
        if (cwd / "pyproject.toml").exists() and "pravidhi" in (cwd / "pyproject.toml").read_text():
            return CheckResult(
                name="Pravidhi package", passed=True, severity="warning",
                message="Running from source (run `pip install -e .` for package mode)",
                fix_command="pip install -e .",
            )
        return CheckResult(
            name="Pravidhi package", passed=False, severity="error",
            message="pravidhi not installed",
            fix_command="pip install pravidhi  # or pip install -e .",
        )


@check("Python dependencies", "warning")
def check_deps(info: SystemInfo) -> CheckResult:
    required = ["click", "rich", "httpx", "pydantic", "yaml", "fastapi", "uvicorn"]
    missing = []
    for mod in required:
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)

    # Handle PyYAML special case
    try:
        import yaml  # noqa: F401
    except ImportError:
        if "yaml" in missing:
            missing.remove("yaml")
            missing.append("pyyaml")

    if missing:
        return CheckResult(
            name="Python dependencies",
            passed=False,
            severity="warning",
            message=f"Missing: {', '.join(missing)}",
            fix_command=f"pip install {' '.join(missing)}",
        )
    return CheckResult(name="Python dependencies", passed=True, message="All core deps installed")


@check("Config file", "warning")
def check_config(info: SystemInfo) -> CheckResult:
    config_paths = [
        Path.cwd() / "pravidhi.yaml",
        Path.home() / ".pravidhi" / "pravidhi.yaml",
        Path(__file__).parent.parent / "pravidhi.yaml",
    ]
    for p in config_paths:
        if p.exists():
            return CheckResult(name="Config file", passed=True, message=f"Found at {p}")
    return CheckResult(
        name="Config file", passed=False, severity="warning",
        message="No pravidhi.yaml found",
        fix_command="pravidhi setup  # or create manually",
    )


@check("Git installed", "warning")
def check_git(info: SystemInfo) -> CheckResult:
    git = shutil.which("git")
    return CheckResult(
        name="Git", passed=git is not None,
        severity="warning",
        message=f"git: {git or 'NOT FOUND'}",
        fix_command=info.package_manager + " install git",
    )


@check("Curl / Wget", "warning")
def check_curl(info: SystemInfo) -> CheckResult:
    curl = shutil.which("curl")
    wget = shutil.which("wget")
    ok = curl is not None or wget is not None
    return CheckResult(
        name="Curl/Wget", passed=ok,
        severity="warning",
        message=f"curl: {curl or '✗'}, wget: {wget or '✗'}",
        fix_command=info.package_manager + " install curl",
    )


@check("OpenRouter API key", "info")
def check_api_key(info: SystemInfo) -> CheckResult:
    key = os.environ.get("OPENROUTER_API_KEY", "")
    return CheckResult(
        name="OpenRouter API key", passed=bool(key),
        severity="info",
        message="OPENROUTER_API_KEY " + ("set ✓" if key else "not set — LLM features won't work"),
        fix_command="export OPENROUTER_API_KEY='sk-or-v1-...'",
    )


@check("Disk space", "warning")
def check_disk(info: SystemInfo) -> CheckResult:
    try:
        stat = os.statvfs(Path.home())
        free_gb = (stat.f_frsize * stat.f_bavail) / (1024 ** 3)
        ok = free_gb > 0.5
        return CheckResult(
            name="Disk space", passed=ok,
            severity="warning",
            message=f"{free_gb:.1f} GB free" if ok else f"CRITICAL: only {free_gb:.1f} GB free",
        )
    except Exception:
        return CheckResult(name="Disk space", passed=True, severity="info", message="Could not check")


@check("Memory", "info")
def check_memory(info: SystemInfo) -> CheckResult:
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if "MemTotal" in line:
                    mem_kb = int(line.split()[1])
                    mem_gb = mem_kb / (1024 ** 2)
                    return CheckResult(
                        name="Memory", passed=mem_gb >= 0.5,
                        severity="info",
                        message=f"{mem_gb:.1f} GB RAM",
                    )
    except FileNotFoundError:
        pass
    return CheckResult(name="Memory", passed=True, severity="info", message="Could not check")


@check("Cron daemon status", "info")
def check_cron(info: SystemInfo) -> CheckResult:
    # Check if our cron DB is accessible
    db_path = Path.home() / ".pravidhi" / "cron.db"
    ok = db_path.exists()
    return CheckResult(
        name="Cron database", passed=ok,
        severity="info",
        message="cron.db " + ("exists" if ok else "not yet created (run `pravidhi cron start`)"),
    )


@check("Skills directory", "info")
def check_skills(info: SystemInfo) -> CheckResult:
    dirs = [
        Path.home() / ".codex" / "skills",
        Path.home() / ".pravidhi" / "skills",
        Path.cwd() / "skills",
    ]
    found = [d for d in dirs if d.exists()]
    return CheckResult(
        name="Skills directories", passed=len(found) > 0,
        severity="info",
        message=f"{len(found)} skill dirs: {', '.join(str(d) for d in found)}" if found else "No skill dirs found",
    )


@check("System packages (Linux)", "warning")
def check_system_packages(info: SystemInfo) -> CheckResult:
    if info.os not in ("linux", "termux"):
        return CheckResult(name="System packages", passed=True, message="Not applicable")

    needed = []
    if info.is_termux:
        for cmd in ["python", "clang", "git", "openssh"]:
            if not shutil.which(cmd):
                needed.append(cmd)
    else:
        for cmd in ["python3", "git", "curl"]:
            if not shutil.which(cmd):
                needed.append(cmd)

    if needed:
        pm = info.package_manager or "apt"
        return CheckResult(
            name="System packages", passed=False,
            severity="warning",
            message=f"Missing: {', '.join(needed)}",
            fix_command=f"{pm} install {' '.join(needed)}",
        )
    return CheckResult(name="System packages", passed=True, message="All system deps found")


@check("Hermes Agent (optional)", "info")
def check_hermes(info: SystemInfo) -> CheckResult:
    hermes = shutil.which("hermes")
    return CheckResult(
        name="Hermes Agent", passed=hermes is not None,
        severity="info",
        message=f"hermes: {hermes or 'not installed (optional)'}",
    )


@check("OpenSSH", "info")
def check_ssh(info: SystemInfo) -> CheckResult:
    ssh = shutil.which("ssh")
    sshpass = shutil.which("sshpass")
    return CheckResult(
        name="OpenSSH", passed=ssh is not None,
        severity="info",
        message=f"ssh: {ssh or '✗'}, sshpass: {sshpass or '✗'}",
        fix_command=info.package_manager + " install openssh-client sshpass",
    )


# ── Doctor Engine ─────────────────────────────────────────────────────────────

class DoctorEngine:
    """Runs diagnostics and optionally repairs issues."""

    def __init__(self):
        self.system = detect_system()

    def diagnose(self) -> List[CheckResult]:
        results = []
        for check_def in CHECKS:
            try:
                result = check_def["fn"](self.system)
                results.append(result)
            except Exception as e:
                results.append(CheckResult(
                    name=check_def["name"],
                    passed=False,
                    severity=check_def.get("severity", "error"),
                    message=f"Check crashed: {e}",
                ))
        return results

    def summary(self, results: List[CheckResult]) -> Dict[str, Any]:
        errors = [r for r in results if not r.passed and r.severity == "error"]
        warnings = [r for r in results if not r.passed and r.severity == "warning"]
        infos = [r for r in results if r.severity == "info"]
        return {
            "total": len(results),
            "passed": sum(1 for r in results if r.passed),
            "failed": sum(1 for r in results if not r.passed),
            "errors": len(errors),
            "warnings": len(warnings),
            "infos": len(infos),
            "fixable": sum(1 for r in results if not r.passed and r.fix_command),
            "system": {
                "os": self.system.os,
                "os_version": self.system.os_version,
                "arch": self.system.arch,
                "python": self.system.python_version,
                "is_termux": self.system.is_termux,
                "is_container": self.system.is_container,
                "is_root": self.system.is_root,
                "package_manager": self.system.package_manager,
            },
        }

    def auto_fix(self, results: List[CheckResult]) -> List[Dict[str, Any]]:
        """Attempt to fix all fixable issues."""
        fixes = []
        failed_items = [r for r in results if not r.passed and r.fix_command]

        for item in failed_items:
            try:
                fix_cmd = item.fix_command
                if fix_cmd.startswith("pip install"):
                    fixes.append(self._fix_pip(fix_cmd, item.name))
                elif fix_cmd.startswith("apt ") or fix_cmd.startswith("pkg "):
                    fixes.append(self._fix_system(fix_cmd, item.name))
                else:
                    fixes.append({
                        "check": item.name,
                        "status": "manual",
                        "message": f"Manual fix needed: {fix_cmd}",
                    })
            except Exception as e:
                fixes.append({
                    "check": item.name,
                    "status": "failed",
                    "message": str(e),
                })
        return fixes

    def _fix_pip(self, cmd: str, name: str) -> Dict[str, Any]:
        """Install Python packages."""
        result = subprocess.run(
            cmd.split() + ["--break-system-packages", "-q"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            return {"check": name, "status": "fixed", "message": f"Installed: {cmd}"}
        else:
            return {"check": name, "status": "failed", "message": result.stderr[:200]}

    def _fix_system(self, cmd: str, name: str) -> Dict[str, Any]:
        """Install system packages."""
        full_cmd = cmd.split()
        if shutil.which("sudo") and not self.system.is_root:
            full_cmd = ["sudo"] + full_cmd
        full_cmd.extend(["-y", "-q"])

        result = subprocess.run(full_cmd, capture_output=True, text=True)
        if result.returncode == 0:
            return {"check": name, "status": "fixed", "message": f"Installed: {cmd}"}
        else:
            return {"check": name, "status": "failed", "message": result.stderr[:200]}


# ── CLI Entry Points ─────────────────────────────────────────────────────────

def run_doctor(fix: bool = False, deps: bool = False) -> int:
    """Run the doctor and optionally fix issues."""
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.columns import Columns

    console = Console()
    engine = DoctorEngine()
    sys_info = engine.system

    console.print(Panel(
        f"[bold cyan]Pravidhi Doctor[/bold cyan]\n"
        f"[dim]OS:[/dim] {sys_info.os}{' (Termux)' if sys_info.is_termux else ''} "
        f"{sys_info.os_version or ''}\n"
        f"[dim]Arch:[/dim] {sys_info.arch}  "
        f"[dim]Python:[/dim] {sys_info.python_version}\n"
        f"[dim]Package Manager:[/dim] {sys_info.package_manager or 'N/A'}  "
        f"[dim]Root:[/dim] {'✓' if sys_info.is_root else '✗'}  "
        f"[dim]Container:[/dim] {'✓' if sys_info.is_container else '✗'}",
        border_style="cyan",
    ))

    results = engine.diagnose()
    summary = engine.summary(results)

    # Results table
    table = Table(box=None)
    table.add_column("Status", width=6)
    table.add_column("Check", style="bold", width=25)
    table.add_column("Message", width=70)

    for r in results:
        if r.passed:
            table.add_row("[green]✓[/green]", r.name, r.message)
        elif r.severity == "error":
            table.add_row("[red]✗[/red]", r.name, f"[red]{r.message}[/red]")
        elif r.severity == "warning":
            table.add_row("[yellow]⚠[/yellow]", r.name, f"[yellow]{r.message}[/yellow]")
        else:
            table.add_row("[dim]i[/dim]", r.name, f"[dim]{r.message}[/dim]")

    console.print(table)

    # Summary
    console.print(f"\n[bold]Summary:[/bold] "
                  f"[green]{summary['passed']} passed[/green], "
                  f"[red]{summary['errors']} errors[/red], "
                  f"[yellow]{summary['warnings']} warnings[/yellow], "
                  f"[dim]{summary['infos']} info[/dim]")

    # Auto-fix
    failed = [r for r in results if not r.passed and r.severity in ("error", "warning")]
    fixable = [r for r in failed if r.fix_command]

    if fix and fixable:
        console.print(f"\n[bold]🔧 Auto-fixing {len(fixable)} issues...[/bold]")
        fixes = engine.auto_fix(results)
        for fix_result in fixes:
            status_icon = {"fixed": "✅", "manual": "📋", "failed": "❌"}.get(fix_result["status"], "➡")
            console.print(f"  {status_icon} {fix_result['check']}: {fix_result['message']}")
        console.print("[green]Auto-fix complete. Run 'pravidhi doctor' again to verify.[/green]")

    elif deps:
        console.print("\n[bold]📦 Installing dependencies...[/bold]")
        fixes = engine.auto_fix([r for r in failed if "dep" in r.name.lower() or "package" in r.name.lower()])
        for fix_result in fixes:
            console.print(f"  {'✅' if fix_result['status'] == 'fixed' else '❌'} {fix_result['check']}: {fix_result['message']}")

    # Final score
    if summary["errors"] == 0:
        console.print(f"\n[green]✓ All critical checks pass[/green]")
        return 0
    else:
        console.print(f"\n[red]✗ {summary['errors']} critical issue(s) need attention[/red]")
        return 1
