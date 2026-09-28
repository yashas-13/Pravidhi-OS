"""Pravidhi Cybersecurity Agent CLI — pentest, scan, skill search.

Usage:
    pravidhi cyber pentest <target> [--intent] [--model]
    pravidhi cyber scan <target> [--command]
    pravidhi cyber skills <query>
    pravidhi cyber mitre <technique_id>
    pravidhi cyber report [--id]
    pravidhi cyber agents
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

import click

logger = logging.getLogger("pravidhi.cyber.cli")


@click.group()
def cyber():
    """🔒 Cybersecurity agent — VulnClaw engine + 817 skills + OpenRouter."""
    pass


@cyber.command()
@click.argument("target")
@click.option("--intent", "-i", default="full pentest",
              help="Pentest intent: recon, discovery, exploitation, full pentest")
@click.option("--model", "-m", default="openai/gpt-5.4-mini",
              help="OpenRouter model")
@click.option("--skills/--no-skills", default=True, help="Use skill augmentation")
@click.option("--output", "-o", type=click.Path(), help="Save report to file")
def pentest(target: str, intent: str, model: str, skills: bool, output: Optional[str]):
    """Run a full penetration test against a target."""
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    console = Console()

    console.print(Panel(f"[bold red]🔒 Pravidhi Cyber Pentest[/bold red]\n"
                        f"Target: [cyan]{target}[/cyan]\n"
                        f"Intent: [yellow]{intent}[/yellow]\n"
                        f"Model:  [green]{model}[/green]",
                        border_style="red"))

    from cyber.agent.core import get_cyber_agent
    agent = get_cyber_agent()

    with console.status("[bold red]Running pentest...") as status:
        report = asyncio.run(agent.pentest(target, intent, model, skills))

    console.print(f"\n[bold]Pentest {'✅ Complete' if report.status == 'completed' else '❌ Failed'}[/bold]")
    console.print(f"Duration: {report.duration:.1f}s")
    console.print(f"Findings: {len(report.findings)}")

    if report.findings:
        table = Table(title="Findings")
        table.add_column("Severity", style="bold")
        table.add_column("Title", style="cyan")
        table.add_column("Phase", style="yellow")
        table.add_column("Skill", style="green")

        severity_color = {
            "critical": "red",
            "high": "orange1",
            "medium": "yellow",
            "low": "blue",
            "info": "white",
        }

        for f in report.findings:
            color = severity_color.get(f.severity, "white")
            table.add_row(
                f"[{color}]{f.severity.upper()}[/{color}]",
                f.title[:60],
                f.phase,
                f.skill_used[:25] if f.skill_used else "-",
            )
        console.print(table)

    if output:
        with open(output, "w") as f:
            json.dump({
                "target": target,
                "status": report.status,
                "duration": report.duration,
                "findings": [
                    {"title": f.title, "severity": f.severity,
                     "phase": f.phase, "description": f.description}
                    for f in report.findings
                ],
            }, f, indent=2)
        console.print(f"[green]Report saved:[/green] {output}")


@cyber.command()
@click.argument("target")
@click.option("--command", "-c", default="nmap -sV", help="Command to run")
@click.option("--model", "-m", default="openai/gpt-5.4-mini")
def scan(target: str, command: str, model: str):
    """Run a single security command against target."""
    from rich.console import Console
    console = Console()

    console.print(f"[bold]Scan:[/bold] {target}")
    console.print(f"[bold]Command:[/bold] {command}")

    from cyber.agent.core import get_cyber_agent
    agent = get_cyber_agent()

    with console.status("[bold]Scanning...") as status:
        result = asyncio.run(agent.scan(target, command, model))

    console.print(Panel(result[:2000] if result else "No output",
                        title="Scan Result", border_style="green"))


@cyber.command()
@click.argument("query")
@click.option("--top-k", "-k", default=10, help="Number of results")
def skills(query: str, top_k: int):
    """Search 817 cybersecurity skills."""
    from rich.console import Console
    from rich.table import Table
    console = Console()

    from cyber.agent.core import get_cyber_agent
    agent = get_cyber_agent()

    results = agent.search_skills(query, top_k)

    console.print(f"[bold]Search:[/bold] '{query}' — {len(results)} results from {agent.total_skills} skills")

    if results:
        table = Table()
        table.add_column("Skill", style="cyan")
        table.add_column("Description", style="white")
        for r in results:
            table.add_row(
                r.get("id", "")[:35],
                r.get("description", "")[:80],
            )
        console.print(table)


@cyber.command("mitre")
@click.argument("technique_id")
def mitre(technique_id: str):
    """Find skills by MITRE ATT&CK technique ID."""
    from rich.console import Console
    from rich.table import Table
    console = Console()

    from cyber.agent.core import get_cyber_agent
    agent = get_cyber_agent()

    results = agent.get_skill_by_mitre(technique_id)

    console.print(f"[bold]MITRE {technique_id}:[/bold] {len(results)} skills mapped")

    if results:
        table = Table()
        table.add_column("Skill", style="cyan")
        table.add_column("Description", style="white")
        for r in results[:20]:
            table.add_row(
                r.get("id", "")[:40],
                r.get("description", "")[:80],
            )
        console.print(table)


@cyber.command()
@click.option("--id", "report_id", help="Report ID (default: latest)")
def report(report_id: Optional[str]):
    """Show pentest report."""
    from rich.console import Console
    console = Console()

    from cyber.agent.core import get_cyber_agent
    agent = get_cyber_agent()

    if not agent.report_store:
        console.print("[yellow]No reports yet. Run a pentest first.[/yellow]")
        return

    r = agent.report_store[-1]
    console.print(f"[bold]Report:[/bold] {r.target.url}")
    console.print(f"[bold]Status:[/bold] {r.status}")
    console.print(f"[bold]Duration:[/bold] {r.duration:.1f}s")
    console.print(f"[bold]Findings:[/bold] {len(r.findings)}")
    for f in r.findings:
        console.print(f"  [{f.severity}] {f.title}")


@cyber.command("agents")
def list_agents():
    """Show cyber agent configuration and status."""
    from rich.console import Console
    from rich.table import Table
    console = Console()

    from cyber.agent.core import get_cyber_agent
    agent = get_cyber_agent()

    console.print("[bold]🔒 Pravidhi Cyber Agent[/bold]")
    console.print(f"  Skills loaded: {agent.total_skills}")
    console.print(f"  Reports: {len(agent.report_store)}")
    console.print(f"  OpenRouter: {'✅ configured' if agent.bridge.openrouter_key else '❌ no key'}")

    has_key = bool(agent.bridge.openrouter_key)
    console.print(f"\n  [dim]Set OPENROUTER_API_KEY env var for LLM access[/dim]" if not has_key else "")
