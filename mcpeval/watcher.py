"""File watcher for development - re-runs checks on schema changes."""

from __future__ import annotations

import time
from pathlib import Path

from .schema import load_spec
from .analyzer import analyze
from .display import console, print_header, print_analysis, print_token_breakdown, print_summary


def watch_file(spec_path: Path, interval: float = 1.0) -> None:
    """Watch a schema file and re-run analysis on changes."""
    last_mtime = 0.0
    last_score = -1

    console.print(f"  [cyan]Watching[/cyan] {spec_path} (Ctrl+C to stop)")
    console.print()

    try:
        while True:
            try:
                mtime = spec_path.stat().st_mtime
            except FileNotFoundError:
                time.sleep(interval)
                continue

            if mtime != last_mtime:
                last_mtime = mtime
                console.clear()
                console.print(f"  [dim]Last change: {time.strftime('%H:%M:%S')}[/dim]")
                console.print()

                try:
                    spec = load_spec(spec_path)
                    report = analyze(spec)

                    print_header(spec)
                    print_analysis(report)
                    print_token_breakdown(spec)
                    print_summary(report)

                    # Show trend
                    if last_score >= 0:
                        delta = report.score - last_score
                        if delta > 0:
                            console.print(f"  [green]Score: +{delta} from last change[/green]")
                        elif delta < 0:
                            console.print(f"  [red]Score: {delta} from last change[/red]")

                    last_score = report.score

                except Exception as e:
                    console.print(f"  [red]Error: {e}[/red]")

            time.sleep(interval)

    except KeyboardInterrupt:
        console.print("\n  [dim]Stopped watching.[/dim]")
