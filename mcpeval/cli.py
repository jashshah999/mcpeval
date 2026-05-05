"""CLI for mcpeval."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import click

from .schema import load_spec
from .analyzer import analyze
from .display import (
    console,
    print_header,
    print_analysis,
    print_simulation,
    print_suggestions,
    print_token_breakdown,
    print_summary,
)


@click.group()
@click.version_option()
def main():
    """mcpeval - Test your MCP servers before shipping."""
    pass


@main.command()
@click.argument("spec_file", type=click.Path(exists=True))
@click.option("--simulate", "-s", is_flag=True, help="Run LLM simulation (requires API key)")
@click.option("--suggest", is_flag=True, help="Get AI-powered improvement suggestions")
@click.option("--provider", "-p", default="gemini", type=click.Choice(["gemini", "openai", "anthropic"]))
@click.option("--model", "-m", default=None, help="Model to use for simulation")
@click.option("--api-key", envvar="MCPEVAL_API_KEY", help="API key (or set GEMINI_API_KEY/OPENAI_API_KEY)")
@click.option("--cases", type=click.Path(exists=True), help="Custom test cases YAML file")
@click.option("--json-output", "-j", is_flag=True, help="Output as JSON")
@click.option("--ci", is_flag=True, help="CI mode: exit 1 on failures")
def check(spec_file, simulate, suggest, provider, model, api_key, cases, json_output, ci):
    """Analyze and test an MCP server schema.

    SPEC_FILE can be:
    - MCP tools JSON ({"tools": [...]})
    - OpenAPI spec (YAML/JSON)
    """
    spec = load_spec(Path(spec_file))

    if json_output:
        _run_json(spec, simulate, suggest, provider, model, api_key, cases, ci)
        return

    print_header(spec)

    # Static analysis
    report = analyze(spec)
    print_analysis(report)
    print_token_breakdown(spec)

    # LLM simulation
    sim_report = None
    if simulate:
        sim_report = asyncio.run(_run_simulation(spec, provider, model, api_key, cases))
        print_simulation(sim_report)

    # AI suggestions
    if suggest:
        suggestions = asyncio.run(_run_suggestions(spec, provider, api_key))
        print_suggestions(suggestions)

    print_summary(report, sim_report)

    if ci:
        if not report.passed:
            sys.exit(1)
        if sim_report and sim_report.accuracy < 0.8:
            sys.exit(1)


@main.command()
@click.argument("spec_file", type=click.Path(exists=True))
def tokens(spec_file):
    """Show token usage breakdown for each tool."""
    spec = load_spec(Path(spec_file))
    print_header(spec)
    print_token_breakdown(spec)


@main.command()
@click.argument("spec_file", type=click.Path(exists=True))
@click.option("--provider", "-p", default="gemini", type=click.Choice(["gemini", "openai", "anthropic"]))
@click.option("--model", "-m", default=None)
@click.option("--api-key", envvar="MCPEVAL_API_KEY")
def improve(spec_file, provider, model, api_key):
    """Get AI-powered suggestions to improve your schemas."""
    spec = load_spec(Path(spec_file))
    print_header(spec)
    suggestions = asyncio.run(_run_suggestions(spec, provider, api_key))
    print_suggestions(suggestions)


@main.command()
@click.argument("spec_file", type=click.Path(exists=True))
@click.option("--output", "-o", type=click.Path(), help="Output file for test cases")
def gen(spec_file, output):
    """Generate test cases from a spec file."""
    import json
    import yaml

    spec = load_spec(Path(spec_file))

    from .simulator import generate_test_cases
    cases = generate_test_cases(spec)

    cases_data = [
        {
            "query": c.query,
            "expected_tool": c.expected_tool,
            "category": c.category,
        }
        for c in cases
    ]

    if output:
        out_path = Path(output)
        if out_path.suffix in (".yaml", ".yml"):
            out_path.write_text(yaml.dump(cases_data, default_flow_style=False))
        else:
            out_path.write_text(json.dumps(cases_data, indent=2))
        console.print(f"  [green]Generated {len(cases)} test cases → {output}[/green]")
    else:
        console.print(json.dumps(cases_data, indent=2))


@main.command()
@click.argument("spec_file", type=click.Path(exists=True))
@click.option("--output", "-o", type=click.Path(), help="Output file (default: overwrites input)")
def fix(spec_file, output):
    """Auto-fix common schema issues (renames, missing descriptions)."""
    from .fixer import auto_fix, export_fixed

    spec = load_spec(Path(spec_file))
    fixed_spec, changes = auto_fix(spec)

    if not changes:
        console.print("  [green]Nothing to fix![/green]")
        return

    for change in changes:
        console.print(f"  [cyan]→[/cyan] {change}")

    out_path = Path(output) if output else Path(spec_file)
    export_fixed(fixed_spec, out_path)
    console.print(f"\n  [green]Fixed {len(changes)} issues → {out_path}[/green]")


@main.command()
@click.argument("command", nargs=-1, required=True)
@click.option("--timeout", "-t", default=10, help="Timeout in seconds")
def connect(command, timeout):
    """Connect to a running MCP server and analyze its tools.

    Example:
        mcpeval connect npx -y @modelcontextprotocol/server-filesystem /tmp
    """
    from .live import connect_stdio

    console.print(f"  Connecting to: {' '.join(command)}")
    try:
        spec = connect_stdio(list(command), timeout=timeout)
        console.print(f"  [green]Connected! Found {len(spec.tools)} tools[/green]")
        print_header(spec)
        report = analyze(spec)
        print_analysis(report)
        print_token_breakdown(spec)
        print_summary(report)
    except RuntimeError as e:
        console.print(f"  [red]Error: {e}[/red]")
        sys.exit(1)


@main.command(name="diff")
@click.argument("before", type=click.Path(exists=True))
@click.argument("after", type=click.Path(exists=True))
@click.option("--ci", is_flag=True, help="Exit 1 on regressions")
def diff_cmd(before, after, ci):
    """Compare two schema versions and detect regressions.

    Example:
        mcpeval diff schema_v1.json schema_v2.json
    """
    from .compare import compare_specs

    result = compare_specs(Path(before), Path(after))

    console.print()
    console.print(f"  [bold]Schema Diff[/bold]: {before} → {after}")
    console.print(f"  Score: {result.score_before} → {result.score_after}", end="")
    delta = result.score_after - result.score_before
    if delta > 0:
        console.print(f" [green](+{delta})[/green]")
    elif delta < 0:
        console.print(f" [red]({delta})[/red]")
    else:
        console.print(" (unchanged)")

    if result.token_delta:
        sign = "+" if result.token_delta > 0 else ""
        color = "red" if result.token_delta > 0 else "green"
        console.print(f"  Tokens: [{color}]{sign}{result.token_delta}[/{color}]")

    if result.added_tools:
        console.print(f"  [green]+ Added:[/green] {', '.join(result.added_tools)}")
    if result.removed_tools:
        console.print(f"  [red]- Removed:[/red] {', '.join(result.removed_tools)}")

    for td in result.changed_tools:
        console.print(f"  [yellow]~ {td.name}:[/yellow] {'; '.join(td.changes)}")

    console.print()
    if result.regressions:
        console.print("  [bold red]Regressions:[/bold red]")
        for r in result.regressions:
            console.print(f"    [red]✗[/red] {r}")
    if result.improvements:
        console.print("  [bold green]Improvements:[/bold green]")
        for imp in result.improvements:
            console.print(f"    [green]✓[/green] {imp}")

    if not result.regressions and not result.improvements:
        console.print("  [dim]No significant changes.[/dim]")

    console.print()
    if ci and result.has_regressions:
        sys.exit(1)


@main.command(name="watch")
@click.argument("spec_file", type=click.Path(exists=True))
def watch_cmd(spec_file):
    """Watch a schema file and re-run analysis on changes.

    Great for development — edit your schema and see the score update live.
    """
    from .watcher import watch_file
    watch_file(Path(spec_file))


@main.command()
@click.argument("spec_file", type=click.Path(exists=True))
@click.option("--format", "-f", "fmt", default="markdown", type=click.Choice(["markdown", "json", "badge"]))
@click.option("--output", "-o", type=click.Path())
def report(spec_file, fmt, output):
    """Generate a report (markdown for PR comments, badge URL, or JSON)."""
    from .report import generate_markdown, generate_badge_url

    spec = load_spec(Path(spec_file))
    report_data = analyze(spec)

    if fmt == "markdown":
        content = generate_markdown(spec, report_data)
    elif fmt == "badge":
        content = generate_badge_url(report_data.score)
    else:
        import json as json_mod
        content = json_mod.dumps({
            "score": report_data.score,
            "grade": "A" if report_data.score >= 90 else "B" if report_data.score >= 80 else "C" if report_data.score >= 60 else "F",
            "tools": len(spec.tools),
            "tokens": spec.total_tokens,
            "errors": report_data.error_count,
            "warnings": report_data.warning_count,
        }, indent=2)

    if output:
        Path(output).write_text(content)
        console.print(f"  [green]Report saved to {output}[/green]")
    else:
        console.print(content)


@main.command()
def init():
    """Create a sample mcpeval config in the current directory."""
    sample = {
        "name": "my-mcp-server",
        "tools": [
            {
                "name": "search_documents",
                "description": "Search for documents by keyword query. Returns matching document titles and snippets.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query string"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of results to return (default: 10)"
                        }
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "get_document",
                "description": "Retrieve the full content of a document by its ID.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "document_id": {
                            "type": "string",
                            "description": "The unique document identifier"
                        }
                    },
                    "required": ["document_id"]
                }
            }
        ]
    }

    import json
    Path("mcpeval.json").write_text(json.dumps(sample, indent=2))
    console.print("  [green]Created mcpeval.json with sample tools[/green]")
    console.print("  [dim]Run: mcpeval check mcpeval.json[/dim]")


async def _run_simulation(spec, provider, model, api_key, cases_file):
    from .simulator import run_simulation, generate_test_cases, SimulationCase

    if cases_file:
        import yaml
        cases_data = yaml.safe_load(Path(cases_file).read_text())
        cases = [SimulationCase(**c) for c in cases_data]
    else:
        cases = generate_test_cases(spec)

    return await run_simulation(spec, cases, provider=provider, model=model, api_key=api_key)


async def _run_suggestions(spec, provider, api_key):
    from .suggestions import suggest_improvements
    return await suggest_improvements(spec, provider=provider, api_key=api_key)


def _run_json(spec, simulate, suggest, provider, model, api_key, cases, ci):
    import json as json_mod

    report = analyze(spec)
    output = {
        "score": report.score,
        "passed": report.passed,
        "errors": report.error_count,
        "warnings": report.warning_count,
        "issues": [
            {"tool": i.tool, "severity": i.severity.value, "code": i.code, "message": i.message}
            for i in report.issues
        ],
        "tokens": {t.name: t.token_estimate for t in spec.tools},
        "total_tokens": spec.total_tokens,
    }

    if simulate:
        sim_report = asyncio.run(_run_simulation(spec, provider, model, api_key, cases))
        output["simulation"] = {
            "accuracy": sim_report.accuracy,
            "total": sim_report.total_cases,
            "correct": sim_report.correct_selections,
            "results": [
                {
                    "query": r.case.query,
                    "expected": r.case.expected_tool,
                    "got": r.selected_tool,
                    "correct": r.correct_tool,
                }
                for r in sim_report.results
            ],
        }

    click.echo(json_mod.dumps(output, indent=2))

    if ci and not report.passed:
        sys.exit(1)
