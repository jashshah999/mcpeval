"""Rich terminal output for mcpeval results."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

from .analyzer import AnalysisReport, Severity
from .simulator import SimulationReport
from .suggestions import Suggestion
from .schema import MCPServerSpec

console = Console()


def print_header(spec: MCPServerSpec) -> None:
    title = Text("mcpeval", style="bold cyan")
    subtitle = Text(f" {spec.name} ", style="dim")
    stats = Text(f"{len(spec.tools)} tools | ~{spec.total_tokens} tokens", style="dim")

    console.print()
    console.print(Panel(
        Text.assemble(title, subtitle, "\n", stats),
        border_style="cyan",
        padding=(0, 2),
    ))
    console.print()


def print_analysis(report: AnalysisReport) -> None:
    # Score display
    score = report.score
    if score >= 80:
        style = "bold green"
        grade = "A" if score >= 90 else "B"
    elif score >= 60:
        style = "bold yellow"
        grade = "C"
    else:
        style = "bold red"
        grade = "D" if score >= 40 else "F"

    console.print(f"  Schema Score: [{style}]{score}/100 ({grade})[/{style}]")
    console.print(f"  Errors: [red]{report.error_count}[/red]  Warnings: [yellow]{report.warning_count}[/yellow]")
    console.print()

    if not report.issues:
        console.print("  [green]No issues found. Your schemas look good![/green]")
        return

    # Issues table
    table = Table(
        show_header=True,
        header_style="bold",
        box=box.SIMPLE,
        padding=(0, 1),
    )
    table.add_column("", width=3)
    table.add_column("Tool", style="cyan", max_width=25)
    table.add_column("Issue", max_width=60)
    table.add_column("Fix", style="dim", max_width=50)

    for issue in sorted(report.issues, key=lambda i: (i.severity != Severity.ERROR, i.severity != Severity.WARNING)):
        icon = _severity_icon(issue.severity)
        table.add_row(icon, issue.tool, issue.message, issue.suggestion)

    console.print(table)


def print_simulation(report: SimulationReport) -> None:
    console.print()
    console.print("  [bold]Simulation Results[/bold]")

    accuracy_style = "green" if report.accuracy >= 0.8 else "yellow" if report.accuracy >= 0.5 else "red"
    console.print(f"  Accuracy: [{accuracy_style}]{report.accuracy:.0%}[/{accuracy_style}] ({report.correct_selections}/{report.total_cases})")
    console.print(f"  Avg latency: {report.avg_latency_ms:.0f}ms")
    console.print()

    table = Table(
        show_header=True,
        header_style="bold",
        box=box.SIMPLE,
        padding=(0, 1),
    )
    table.add_column("", width=3)
    table.add_column("Query", max_width=40)
    table.add_column("Expected", style="cyan", max_width=20)
    table.add_column("Got", max_width=20)
    table.add_column("Time", style="dim", width=8)

    for r in report.results:
        icon = "[green]✓[/green]" if r.correct_tool else "[red]✗[/red]"
        expected = r.case.expected_tool or "[dim]none[/dim]"
        got = r.selected_tool or "[dim]none[/dim]"
        got_style = "green" if r.correct_tool else "red"
        time_str = f"{r.latency_ms:.0f}ms"

        table.add_row(
            icon,
            _truncate(r.case.query, 40),
            expected,
            f"[{got_style}]{got}[/{got_style}]",
            time_str,
        )

    console.print(table)

    # Show failures detail
    failures = [r for r in report.results if not r.correct_tool]
    if failures:
        console.print()
        console.print("  [bold red]Failed cases:[/bold red]")
        for f in failures:
            console.print(f"    [dim]Query:[/dim] {f.case.query}")
            console.print(f"    [dim]Expected:[/dim] {f.case.expected_tool or 'no tool'} → [red]Got:[/red] {f.selected_tool or 'no tool'}")
            if f.reasoning:
                console.print(f"    [dim]Reasoning:[/dim] {f.reasoning}")
            console.print()


def print_suggestions(suggestions: list[Suggestion]) -> None:
    if not suggestions:
        return

    console.print()
    console.print("  [bold]AI Suggestions[/bold]")
    console.print()

    for i, s in enumerate(suggestions, 1):
        console.print(f"  [cyan]{i}.[/cyan] [bold]{s.tool}[/bold] ({s.category})")
        console.print(f"     [red]- {s.original}[/red]")
        console.print(f"     [green]+ {s.improved}[/green]")
        console.print(f"     [dim]{s.reason}[/dim]")
        console.print()


def print_token_breakdown(spec: MCPServerSpec) -> None:
    console.print()
    console.print("  [bold]Token Budget[/bold]")

    table = Table(
        show_header=True,
        header_style="bold",
        box=box.SIMPLE,
        padding=(0, 1),
    )
    table.add_column("Tool", style="cyan")
    table.add_column("Tokens", justify="right")
    table.add_column("% Budget", justify="right")
    table.add_column("", width=30)

    total = spec.total_tokens
    for tool in sorted(spec.tools, key=lambda t: t.token_estimate, reverse=True):
        tokens = tool.token_estimate
        pct = tokens / max(total, 1) * 100
        bar_width = int(pct / 100 * 25)
        bar = "█" * bar_width + "░" * (25 - bar_width)

        color = "green" if tokens < 200 else "yellow" if tokens < 500 else "red"
        table.add_row(
            tool.name,
            f"[{color}]{tokens}[/{color}]",
            f"{pct:.0f}%",
            f"[{color}]{bar}[/{color}]",
        )

    table.add_row("", "", "", "")
    table.add_row("[bold]Total[/bold]", f"[bold]{total}[/bold]", "100%", "")

    console.print(table)


def print_summary(report: AnalysisReport, sim_report: SimulationReport | None = None) -> None:
    console.print()
    parts = []
    if report.passed:
        parts.append("[green]PASS[/green] Static analysis")
    else:
        parts.append(f"[red]FAIL[/red] Static analysis ({report.error_count} errors)")

    if sim_report:
        if sim_report.accuracy >= 0.8:
            parts.append(f"[green]PASS[/green] Simulation ({sim_report.accuracy:.0%})")
        else:
            parts.append(f"[red]FAIL[/red] Simulation ({sim_report.accuracy:.0%})")

    console.print(Panel(
        "\n".join(f"  {p}" for p in parts),
        title="Summary",
        border_style="cyan",
        padding=(0, 2),
    ))
    console.print()


def _severity_icon(severity: Severity) -> str:
    if severity == Severity.ERROR:
        return "[red]✗[/red]"
    elif severity == Severity.WARNING:
        return "[yellow]![/yellow]"
    return "[dim]·[/dim]"


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len - 1] + "…"
