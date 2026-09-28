"""Pravidhi CLI — main entry point for the self-progressive AI ecosystem.

Usage:
    pravidhi chat          Start interactive chat session
    pravidhi cron start    Start offline cron daemon
    pravidhi cron list     List cron jobs
    pravidhi cron add      Add a cron job
    pravidhi research      Run auto-research cycle
    pravidhi status        Show system status
    pravidhi serve         Start API server
    pravidhi skills        List discovered skills
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Optional

import click

from engine.config import get_config, reload_config
from engine.registry import get_registry
from engine.pipeline import Pipeline
from engine.validator import ValidationEngine

logger = logging.getLogger("pravidhi.cli")


# ── Common Options ───────────────────────────────────────────────────────────

def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


# ── CLI Group ────────────────────────────────────────────────────────────────

@click.group()
@click.option("--config", "-c", help="Path to config file", default=None)
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
@click.version_option(version="0.1.0", prog_name="pravidhi")
@click.pass_context
def cli(ctx: click.Context, config: Optional[str], verbose: bool):
    """Pravidhi — Self-progressive AI ecosystem.

    A non-stop self-improving agent harness with offline cron,
    auto-research, multi-layer validation, and universal MCP/plugin/skill integration.
    """
    _setup_logging(verbose)
    ctx.ensure_object(dict)

    if config:
        os.environ["PRAVIDHI_CONFIG_PATH"] = config
        reload_config()

    # Initialize registry
    registry = get_registry()
    registry.discover_skills()


# ── Chat ─────────────────────────────────────────────────────────────────────

# ── Bounty Commands ────────────────────────────────────────────────────────

@cli.group()
def bounty():
    """Vibe Buy Bounty system — post, claim, complete bounties."""
    pass


@bounty.command()
@click.option("--status", default="open", help="Filter by status")
@click.option("--category", default="", help="Filter by category")
def list(status, category):
    """List bounties."""
    import asyncio
    from engine.bounty import BountyBoard
    async def _run():
        board = BountyBoard()
        bounties = await board.list_bounties(status, category)
        stats = await board.get_stats()
        click.echo(click.style(f"Bounty Board ({stats["total_bounties"]} total)", fg="cyan", bold=True))
        click.echo(f"  Open: {stats['open_bounties']}  Completed: {stats['completed_bounties']}  Hunters: {stats['active_hunters']}")
        for b in bounties[:10]:
            click.echo(f"  [{b['id']}] {b['title']} — {b['reward']} ({b['severity']})")
    asyncio.run(_run())


@bounty.command()
@click.argument("title")
@click.option("--description", "-d", default="", help="Description")
@click.option("--reward", "-r", default=0, type=float, help="Reward in VIBE")
@click.option("--severity", default="medium", type=click.Choice(["low","medium","high","critical"]))
def create(title, description, reward, severity):
    """Create a new bounty."""
    import asyncio
    from engine.bounty import BountyBoard
    async def _run():
        board = BountyBoard()
        b = await board.create_bounty(title=title, description=description,
                                        reward_amount=reward, severity=severity)
        click.echo(click.style(f"Bounty created: {b.id[:8]} — {b.title}", fg="green"))
        click.echo(f"  Reward: {b.reward_amount} VIBE  Status: {b.status}")
    asyncio.run(_run())


@bounty.command()
@click.argument("bounty_id")
@click.argument("hunter")
def claim(bounty_id, hunter):
    """Claim a bounty."""
    import asyncio
    from engine.bounty import BountyBoard
    async def _run():
        board = BountyBoard()
        success, msg = await board.claim_bounty(bounty_id, hunter)
        if success:
            click.echo(click.style(f"✅ {msg}", fg="green"))
        else:
            click.echo(click.style(f"❌ {msg}", fg="red"))
    asyncio.run(_run())


# ── Publish Commands ─────────────────────────────────────────────────────────

@cli.group()
def publish():
    """Publish Pravidhi apps to Anyclaw hosting."""
    pass


@publish.command()
def chat():
    """Publish the Pravidhi Chat SPA to Anyclaw."""
    import asyncio
    from engine.publisher import AppPublisher
    async def _run():
        click.echo(click.style("Publishing Pravidhi Chat...", fg="yellow"))
        result = await AppPublisher.publish_chat_ui()
        if result.success:
            click.echo(click.style(f"✅ Published! Claim at: {result.claim_url}", fg="green"))
        else:
            click.echo(click.style(f"❌ Failed: {result.error}", fg="red"))
    asyncio.run(_run())


@publish.command()
def list():
    """List published apps."""
    import asyncio
    from engine.publisher import AppPublisher
    async def _run():
        publisher = AppPublisher()
        apps = await publisher.list_apps()
        if apps:
            click.echo(click.style(f"Published Apps ({len(apps)}):", fg="cyan", bold=True))
            for a in apps[:10]:
                click.echo(f"  • {a.get('app_id','?')}: {a.get('title','')}")
        else:
            click.echo("No apps published yet.")
    asyncio.run(_run())


# ── Interactive Session ──────────────────────────────────────────────────────

@cli.command()
@click.option("--model", "-m", help="Model to use")
@click.option("--provider", "-p", help="Provider to use")
def chat(model: Optional[str], provider: Optional[str]):
    """Start an interactive chat session."""
    config = get_config()
    click.echo(click.style("╔══════════════════════════════════════╗", fg="cyan"))
    click.echo(click.style("║     Pravidhi Interactive Session     ║", fg="cyan"))
    click.echo(click.style("╚══════════════════════════════════════╝", fg="cyan"))
    click.echo(f" Model: {model or config.providers.default_model}")
    click.echo(f" Skills: {len(get_registry().skills)} registered")
    click.echo(f" Tools:  {len(get_registry().list_tools())} available")
    click.echo(" Type '/quit' to exit, '/help' for commands\n")

    pipeline = Pipeline()

    while True:
        try:
            user_input = click.prompt(click.style("▶", fg="green"), prompt_suffix=" ")
        except (EOFError, KeyboardInterrupt):
            click.echo()
            break

        if not user_input:
            continue
        if user_input.lower() in ("/quit", "/exit", "/q"):
            break
        if user_input.lower() == "/help":
            _show_help()
            continue
        if user_input.lower() == "/status":
            _show_status()
            continue

        # Run through pipeline
        with click.progressbar(length=7, label="Processing") as bar:
            async def run():
                ctx = await pipeline.run(user_input)
                return ctx
            ctx = asyncio.run(run())

        # Display result
        if ctx.errors:
            click.echo(click.style(f"\n⚠ {len(ctx.errors)} issues:", fg="yellow"))
            for err in ctx.errors[:3]:
                click.echo(f"  • {err}")

        output = ctx.final_output.get("content", str(ctx.final_output)) if ctx.final_output else "(no output)"
        click.echo()
        click.echo(click.style("Response:", fg="cyan", bold=True))
        click.echo(output[:2000])

        # Show validation score
        score = ctx.validation_score
        score_color = "green" if score >= 0.8 else "yellow" if score >= 0.5 else "red"
        click.echo(click.style(f"\nValidation: {score:.0%}", fg=score_color))


# ── Cron ─────────────────────────────────────────────────────────────────────

@cli.group()
def cron():
    """Manage offline cron jobs (independent daemon)."""
    pass


@cron.command()
@click.option("--db", default="~/.pravidhi/cron.db", help="Database path")
def start(db: str):
    """Start the independent cron scheduler daemon."""
    click.echo("Starting Pravidhi cron daemon (independent, offline)...")
    from cron.scheduler import start_daemon
    start_daemon(db)


@cron.command()
@click.option("--db", default="~/.pravidhi/cron.db", help="Database path")
def list(db: str):
    """List all cron jobs."""
    from cron.scheduler import list_jobs
    list_jobs(db)


@cron.command()
@click.argument("name")
@click.argument("schedule")
@click.option("--command", "-c", help="Command to run (no-agent mode)")
@click.option("--prompt", "-p", help="Prompt to send (agent mode)")
@click.option("--db", default="~/.pravidhi/cron.db", help="Database path")
def add(name: str, schedule: str, command: Optional[str], prompt: Optional[str], db: str):
    """Add a cron job."""
    from cron.scheduler import add_job
    add_job(name, schedule, command=command or "", prompt=prompt or "", db_path=db)


@cron.command()
@click.argument("job_id")
@click.option("--db", default="~/.pravidhi/cron.db", help="Database path")
def pause(job_id: str, db: str):
    """Pause a cron job."""
    from cron.scheduler import CronDB
    db_conn = CronDB(db)
    db_conn.pause_job(job_id)
    click.echo(f"Paused job: {job_id}")


@cron.command()
@click.argument("job_id")
@click.option("--db", default="~/.pravidhi/cron.db", help="Database path")
def resume(job_id: str, db: str):
    """Resume a paused cron job."""
    from cron.scheduler import CronDB
    db_conn = CronDB(db)
    db_conn.resume_job(job_id)
    click.echo(f"Resumed job: {job_id}")


# ── Research ─────────────────────────────────────────────────────────────────

@cli.group()
def research():
    """Auto-research engine commands."""
    pass


@research.command()
def cycle():
    """Run one auto-research cycle."""
    import asyncio
    click.echo("Running auto-research cycle...")
    from research.training_loop import run_research_cycle
    result = asyncio.run(run_research_cycle())
    click.echo(f"\nResearch cycle complete:")
    click.echo(f"  Epoch:      {result['epoch']}")
    click.echo(f"  Accuracy:   {result['accuracy']:.1%}")
    click.echo(f"  Loss:       {result['loss']:.3f}")
    click.echo(f"  Skills:     {len(result['skills_generated'])} new")
    click.echo(f"  Patterns:   {result['error_patterns_found']} errors, {result['success_patterns_found']} successes")
    if result['converged']:
        click.echo(click.style("  ✓ CONVERGED", fg="green", bold=True))


@research.command()
def status():
    """Show research engine status."""
    from research.training_loop import TrainingLoop
    loop = TrainingLoop()
    status = loop.get_status()
    click.echo("Research Engine Status:")
    click.echo(f"  Epoch:        {status['current_epoch']}")
    click.echo(f"  Accuracy:     {status['accuracy']:.1%}")
    click.echo(f"  Loss:         {status['loss']:.3f}")
    click.echo(f"  Total Steps:  {status['total_steps']}")
    click.echo(f"  Converged:    {'✓' if status['converged'] else '○'}")
    if status.get("intent_breakdown"):
        click.echo("  By Intent:")
        for intent, data in status["intent_breakdown"].items():
            pct = data["success"] / data["count"] * 100 if data["count"] else 0
            click.echo(f"    {intent:15} {data['count']:4} runs  {pct:5.1f}% success")


# ── Serve ────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--host", default="127.0.0.1", help="Bind address")
@click.option("--port", default=8642, help="Port")
def serve(host: str, port: int):
    """Start the OpenAI-compatible API server."""
    click.echo(f"Starting Pravidhi API server on http://{host}:{port}")
    from gateway.api_server import start_server
    start_server(host=host, port=port)


# ── Status ────────────────────────────────────────────────────────────────────

@cli.command()
def status():
    """Show system status."""
    _show_status()


# ── Skills ───────────────────────────────────────────────────────────────────

@cli.command()
def skills():
    """List discovered skills."""
    registry = get_registry()
    skills = registry.skills
    if not skills:
        click.echo("No skills discovered.")
        return
    click.echo(f"Discovered {len(skills)} skills:")
    for name, skill in skills.items():
        click.echo(f"  {click.style(name, bold=True):30} {skill.description[:60]}")


# ── Validate (test a prompt) ──────────────────────────────────────────────────

@cli.command()
@click.argument("prompt")
def validate(prompt: str):
    """Validate a prompt through the multi-layer validation engine."""
    import asyncio
    asyncio.run(_validate_inner(prompt))

async def _validate_inner(prompt: str):
    validator = ValidationEngine()
    validator.add_behavioral_rule("Response must address the user's request directly")
    validator.add_behavioral_rule("Response must not contain harmful content")
    from engine.pipeline import IngestStage
    ingest = IngestStage()
    from engine.pipeline import PipelineContext
    ctx = PipelineContext(user_input=prompt)
    ctx = await ingest.handle(ctx)
    reports = await validator.validate(
        input_data={"text": prompt, "type": ctx.parsed_intent.get("type", "general")},
        output_data={"parsed": ctx.parsed_intent},
    )
    score = validator.overall_score(reports)
    passed = validator.all_passed(reports)
    click.echo(f"Validation result: {click.style('PASS' if passed else 'FAIL', bold=True, fg='green' if passed else 'red')}")
    click.echo(f"Overall score: {score:.1%}")
    for layer, report in reports.items():
        color = "green" if report.passed else "red"
        click.echo(f"  {layer:15} {click.style('✓', fg=color) if report.passed else click.style('✗', fg='red')}  score={report.score:.1%}")
        for err in report.errors[:3]:
            click.echo(f"    └─ {err}")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _show_help():
    click.echo("""
Commands:
  /quit        Exit the session
  /help        Show this help
  /status      Show system status
  /skills      List available skills

Pipeline stages: ingest → validate → decompose → route → execute → validate → learn
""")


def _show_status():
    config = get_config()
    registry = get_registry()
    summary = registry.summary()

    click.echo(click.style("╔══════════════════════════════════════╗", fg="cyan"))
    click.echo(click.style("║        Pravidhi System Status        ║", fg="cyan"))
    click.echo(click.style("╚══════════════════════════════════════╝", fg="cyan"))
    click.echo(f" Version:      {config.engine.version}")
    click.echo(f" Engine:       {config.engine.name}")
    click.echo(f" Pipeline:     {'enabled' if config.engine.pipeline.enabled else 'disabled'}")
    click.echo(f" Cron:         {'enabled' if config.cron.enabled else 'disabled'}")
    click.echo(f" Research:     {'enabled' if config.research.enabled else 'disabled'}")
    click.echo(f" Default Model: {config.providers.default_model}")
    click.echo(f" Registry:")
    click.echo(f"   Tools:      {summary['tools']}")
    click.echo(f"   MCP:        {summary['mcp_servers']}")
    click.echo(f"   Skills:     {summary['skills']}")
    click.echo(f"   Plugins:    {summary['plugins']}")
    click.echo(f"   Hooks:      {summary['hooks']}")
    click.echo(f"   Providers:  {summary['providers']}")


# ── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cli()

# ═══════════════════════════════════════════════════════════════════════════════
# Doctor — Diagnostics & Repair
# ═══════════════════════════════════════════════════════════════════════════════

@cli.group()
def doctor():
    """🔧 System diagnostics, dependency repair, and auto-setup."""
    pass


@doctor.command()
@click.option("--fix", is_flag=True, help="Auto-fix all detected issues")
@click.option("--deps", is_flag=True, help="Install missing dependencies only")
@click.pass_context
def run(ctx, fix, deps):
    """Run full system diagnostics and optionally repair issues."""
    from gateway.doctor import run_doctor
    exit_code = run_doctor(fix=fix, deps=deps)
    ctx.exit(exit_code)


@doctor.command()
def version():
    """Show version and system info."""
    from gateway.doctor import detect_system
    info = detect_system()
    click.echo(f"Pravidhi v{get_config().engine.version}")
    click.echo(f"OS: {info.os} {info.os_version or ''}")
    click.echo(f"Arch: {info.arch}")
    click.echo(f"Python: {info.python_version}")
    click.echo(f"Pravidhi home: {info.pravidhi_home}")
    click.echo(f"Termux: {'✓' if info.is_termux else '✗'}")
    click.echo(f"Root: {'✓' if info.is_root else '✗'}")


@doctor.command()
@click.argument("url", default="https://pravidhisolutions.in")
def ping(url):
    """Test network connectivity to a host."""
    import httpx
    try:
        r = httpx.get(url, timeout=10)
        click.echo(f"  {url}")
        click.echo(f"  Status: {r.status_code} {r.reason_phrase}")
        click.echo(f"  Time:   {r.elapsed.total_seconds():.2f}s")
        if r.status_code < 400:
            click.echo(click.style("  ✓ Reachable", fg="green"))
        else:
            click.echo(click.style(f"  ✗ HTTP error", fg="red"))
    except Exception as e:
        click.echo(click.style(f"  ✗ {e}", fg="red"))


@doctor.command()
def install_script():
    """Print the curl install command."""
    click.echo("Linux / macOS:")
    click.echo("  curl -fsSL https://raw.githubusercontent.com/yashas-13/pravidhi/main/scripts/install.sh | bash")
    click.echo("")
    click.echo("Termux (Android):")
    click.echo("  pkg install curl -y && curl -fsSL https://raw.githubusercontent.com/yashas-13/pravidhi/main/scripts/install.sh | bash")
    click.echo("")
    click.echo("Direct one-liner:")
    click.echo('  bash -c "$(curl -fsSL https://raw.githubusercontent.com/yashas-13/pravidhi/main/scripts/install.sh)"')

# ═══════════════════════════════════════════════════════════════════════════════
# Google Labs — DESIGN.md & Skills CLI
# ═══════════════════════════════════════════════════════════════════════════════

@cli.group()
def design():
    """DESIGN.md — design token linting, diff, and export."""
    pass


@design.command()
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option("--json", "json_output", is_flag=True, help="Output raw JSON")
def lint(file, json_output):
    """Lint a DESIGN.md file against the spec."""
    import json
    from engine.google_labs_tools import lint_design_md
    content = file.read_text()
    result = lint_design_md(content)

    if json_output:
        click.echo(json.dumps(result, indent=2))
        return

    status_color = "green" if result["valid"] else "red"
    click.echo(click.style(f"\nDESIGN.md Lint — {file.name}", bold=True))
    click.echo(click.style(f"  Valid: {'✓' if result['valid'] else '✗'}", fg=status_color))
    click.echo(f"  Errors: {result['summary']['errors']}, Warnings: {result['summary']['warnings']}")
    click.echo("")
    for finding in result["findings"]:
        sev = finding["severity"]
        color = {"error": "red", "warning": "yellow", "info": "blue"}.get(sev, "white")
        click.echo(f"  {click.style(f'[{sev.upper():7}]', fg=color)} {finding['message']}")


@design.command()
@click.argument("before", type=click.Path(exists=True, path_type=Path))
@click.argument("after", type=click.Path(exists=True, path_type=Path))
def diff(before, after):
    """Compare two DESIGN.md files."""
    from engine.google_labs_tools import diff_design_md
    result = diff_design_md(before.read_text(), after.read_text())
    click.echo(click.style("\nDESIGN.md Diff", bold=True))
    if result["tokens"]["added"]:
        click.echo(f"  {click.style('Added:', fg='green')}    {', '.join(result['tokens']['added'])}")
    if result["tokens"]["removed"]:
        click.echo(f"  {click.style('Removed:', fg='red')}  {', '.join(result['tokens']['removed'])}")
    if result["tokens"]["modified"]:
        click.echo(f"  {click.style('Modified:', fg='yellow')} {', '.join(result['tokens']['modified'])}")
    click.echo(f"  Regression: {click.style('YES' if result['regression'] else 'NO', fg='red' if result['regression'] else 'green')}")


@design.command()
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option("--format", "-f", type=click.Choice(["json-tailwind", "css-tailwind", "dtcg"]), default="json-tailwind")
def export(file, format):
    """Export DESIGN.md tokens to another format."""
    from engine.google_labs_tools import export_design_md
    result = export_design_md(file.read_text(), format)
    click.echo(result)


@design.command()
def spec():
    """Show DESIGN.md format specification."""
    from engine.google_labs_tools import parse_design_md, DESIGN_MD_LINT_RULES
    click.echo(click.style("DESIGN.md Format Specification (alpha)", bold=True))
    click.echo("")
    click.echo("Required top-level: colors")
    click.echo("Optional: version, name, description, typography, rounded, spacing, components")
    click.echo("")
    click.echo("Section order:")
    for i, sec in enumerate(["Overview", "Colors", "Typography", "Layout & Spacing", "Elevation & Depth", "Shapes", "Components", "Do's and Don'ts"], 1):
        click.echo(f"  {i}. {sec}")
    click.echo("")
    click.echo("Lint rules:")
    for rule in DESIGN_MD_LINT_RULES:
        click.echo(f"  • {rule}")


@cli.group()
def dx():
    """Agent Developer Experience tools."""
    pass


@dx.command()
@click.argument("cli_name")
@click.option("--scores", help="JSON dict of axis scores, e.g. '{\"machine_readable_output\": 2}'")
def cli_scale(cli_name, scores):
    """Score a CLI on the Agent DX Scale (0-21)."""
    import json
    from engine.google_labs_tools import score_cli
    scores_dict = json.loads(scores) if scores else {}
    result = score_cli(cli_name, scores_dict)

    click.echo(click.style(f"\nAgent DX CLI Scale: {cli_name}", bold=True))
    click.echo(f"  Score: {result['total_score']}/{result['max_score']} ({result['percentage']}%)")
    click.echo(f"  Grade: {result['grade']}")
    click.echo("")
    for axis, data in result["per_axis"].items():
        bar = "█" * data["score"] + "░" * (data["max"] - data["score"])
        color = "green" if data["score"] >= 2 else "yellow" if data["score"] >= 1 else "red"
        click.echo(f"  {click.style(axis.replace('_', ' ').title() + ': ' + bar, fg=color)}  {data['score']}/3")
    if result["recommendations"]:
        click.echo(click.style("\nRecommendations:", bold=True))
        for rec in result["recommendations"][:3]:
            click.echo(f"  • {rec}")


@cli.group()
def tdd():
    """Red-Green-Refactor TDD workflow."""
    pass


@tdd.command()
@click.option("--description", "-d", required=True, help="Feature description")
@click.option("--language", "-l", default="typescript", type=click.Choice(["typescript", "python"]))
def cycle(description, language):
    """Generate a TDD Red-Green-Refactor cycle."""
    from engine.google_labs_tools import generate_tdd_cycle
    result = generate_tdd_cycle(description, language)

    click.echo(click.style(f"\nTDD Cycle: {result['feature']}", bold=True))
    click.echo(f"  Language: {result['language']}")
    click.echo(f"  Framework: {result['framework']}")
    click.echo("")
    for phase_key, phase in result["phases"].items():
        click.echo(click.style(f"  [{phase_key.upper()}]", bold=True))
        for step in phase["steps"]:
            click.echo(f"    {step}")
        click.echo("")


@cli.group()
def contracts():
    """Typed Service Contracts (Spec & Handler pattern)."""
    pass


@contracts.command()
@click.argument("name")
@click.option("--operations", "-o", help="JSON array of operation definitions")
def generate(name, operations):
    """Generate a Typed Service Contract."""
    import json
    from engine.google_labs_tools import generate_service_contract
    ops = json.loads(operations) if operations else [{
        "name": f"{name.lower()}_execute",
        "input_schema": {"payload": "string"},
        "output_schema": {"result": "string"},
        "error_types": ["ValidationError"],
    }]
    result = generate_service_contract(name, ops)
    click.echo(result)


@cli.group()
def ink():
    """@json-render/ink — terminal UI from JSON specs."""
    pass


@ink.command()
@click.option("--spec", "-s", help="JSON spec (inline)")
@click.option("--file", "-f", type=click.Path(exists=True, path_type=Path), help="JSON spec file")
def render(spec, file):
    """Generate @json-render/ink code from a JSON spec."""
    import json
    from engine.google_labs_tools import render_ink_spec
    if file:
        spec_content = file.read_text()
    else:
        spec_content = spec
    spec_obj = json.loads(spec_content)
    result = render_ink_spec(spec_obj)
    click.echo(result)


# Register google-labs tools on import
from engine.google_labs_tools import register_all_tools
from cyber.cli.commands import cyber as cyber_group
register_all_tools()


# Add cyber command group

# ── Reverse Engineering CLI ──────────────────────────────────────────

@cli.group()
def re():
    """🔬 Reverse engineering tools — Ghidra, z3, LLM decompilation."""
    pass


@re.command()
@click.argument("path")
@click.option("--depth", "-d", type=click.Choice(["basic", "deep", "full"]), default="basic")
@click.option("--json-output", "-j", is_flag=True, help="Raw JSON output")
def analyze(path, depth, json_output):
    """Analyze a binary file (PE, ELF, Mach-O, firmware)."""
    import json as _json
    from engine.reverse_engineering import BinaryAnalyzer
    from rich.console import Console
    from rich.table import Table
    console = Console()

    import asyncio
    async def run():
        analyzer = BinaryAnalyzer()
        report = await analyzer.analyze(path, depth)
        return report

    with console.status("[bold]Analyzing binary..."):
        report = asyncio.run(run())

    if json_output:
        console.print(_json.dumps({
            "format": report.binary.format.value,
            "arch": report.binary.arch,
            "size": report.binary.size,
            "entropy": report.binary.entropy,
            "strings": len(report.binary.strings),
            "hashes": report.binary.hashes,
            "vulnerabilities": len(report.vulnerabilities),
            "summary": report.summary,
        }, indent=2))
        return

    console.print(f"\n[bold]Binary Analysis:[/bold] {path}")
    console.print(f"  Format: [cyan]{report.binary.format.value}[/cyan]  Arch: [green]{report.binary.arch}[/green]")
    console.print(f"  Size: {report.binary.size:,} bytes  Entropy: {report.binary.entropy:.2f}")
    console.print(f"  Strings: {len(report.binary.strings)}  Vulnerabilities: {len(report.vulnerabilities)}")
    if report.binary.hashes:
        console.print(f"  MD5: [dim]{report.binary.hashes.get('md5', '')}[/dim]")
        console.print(f"  SHA256: [dim]{report.binary.hashes.get('sha256', '')}[/dim]")
    console.print(f"\n{report.summary}")


# ── Router Agent CLI ─────────────────────────────────────────────────

@cli.group()
def router():
    """🌐 9Router agent — model-agnostic pentesting via OpenRouter."""
    pass


@router.command()
@click.argument("target")
@click.option("--intent", "-i", default="full pentest", help="Pentest intent")
@click.option("--model", "-m", default="", help="OpenRouter model")
@click.option("--output", "-o", type=click.Path(), help="Save report to file")
def pentest(target, intent, model, output):
    """Run a penetration test through OpenRouter."""
    import json as _json
    from router_agent.core import NineRouterAgent
    from rich.console import Console
    console = Console()

    console.print(f"[bold red]🌐 Router Pentest:[/bold red] {target}")

    import asyncio
    async def run():
        agent = NineRouterAgent()
        report = await agent.pentest(target, intent, model or agent.default_model)
        return report

    with console.status("[bold]Running pentest..."):
        report = asyncio.run(run())

    console.print(f"\n[bold]Status:[/bold] {report.status}")
    console.print(f"Duration: {report.duration:.1f}s  Findings: {len(report.findings)}")
    console.print(f"Model: {report.model_used}")

    if report.findings:
        from rich.table import Table
        table = Table(title="Findings")
        table.add_column("Severity", style="bold")
        table.add_column("Title", style="cyan")
        table.add_column("Phase")
        severity_color = {"critical": "red", "high": "orange1", "medium": "yellow", "low": "blue", "info": "white"}
        for f in report.findings:
            color = severity_color.get(f.severity, "white")
            table.add_row(f"[{color}]{f.severity.upper()}[/{color}]", f.title[:60], f.phase)
        console.print(table)

    if output:
        with open(output, "w") as f:
            _json.dump({
                "target": target,
                "status": report.status,
                "findings": [{"title": f.title, "severity": f.severity, "description": f.description} for f in report.findings],
            }, f, indent=2)
        console.print(f"[green]Report saved: {output}[/green]")

    if report.summary:
        console.print(f"\n[dim]{report.summary[:500]}[/dim]")


@router.command()
@click.argument("target")
@click.option("--command", "-c", default="nmap -sV", help="Command")
def scan(target, command):
    """Run a security scan through OpenRouter."""
    from router_agent.core import NineRouterAgent
    from rich.console import Console
    console = Console()

    import asyncio
    async def run():
        agent = NineRouterAgent()
        return await agent.scan(target, command)

    with console.status("[bold]Scanning..."):
        result = asyncio.run(run())

    from rich.panel import Panel
    console.print(Panel(result[:2000] if result else "No output", title="Scan Result", border_style="green"))


@router.command()
def models():
    """List available OpenRouter models."""
    from router_agent.core import NineRouterAgent
    from rich.console import Console
    from rich.table import Table
    console = Console()

    agent = NineRouterAgent()
    model_list = agent.list_models()

    console.print(f"[bold]Available Models:[/bold] {len(model_list)}")
    table = Table()
    table.add_column("Model ID", style="cyan")
    for m in model_list[:30]:
        table.add_row(m)
    console.print(table)
    if len(model_list) > 30:
        console.print(f"[dim]... and {len(model_list) - 30} more[/dim]")


# ── Enhanced Doctor ──────────────────────────────────────────────────

@cli.command()
@click.option("--fix", is_flag=True, help="Auto-fix all issues")
@click.option("--deps", is_flag=True, help="Install missing dependencies")
@click.option("--full", is_flag=True, help="Full comprehensive check")
def doctor(fix, deps, full):
    """System diagnostics, dependency repair, and auto-setup."""
    from gateway.doctor import run_doctor as _run_doctor
    import sys
    sys.exit(_run_doctor(fix=fix, deps=deps))

cli.add_command(cyber_group)
