"""Compare two MCP schema versions and report regressions."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .schema import Tool, load_spec
from .analyzer import analyze


@dataclass
class SchemaDiff:
    added_tools: list[str] = field(default_factory=list)
    removed_tools: list[str] = field(default_factory=list)
    changed_tools: list[ToolDiff] = field(default_factory=list)
    score_before: int = 0
    score_after: int = 0
    token_delta: int = 0
    regressions: list[str] = field(default_factory=list)
    improvements: list[str] = field(default_factory=list)

    @property
    def has_regressions(self) -> bool:
        return len(self.regressions) > 0 or self.score_after < self.score_before


@dataclass
class ToolDiff:
    name: str
    changes: list[str] = field(default_factory=list)


def compare_specs(before_path: Path, after_path: Path) -> SchemaDiff:
    """Compare two schema versions and identify regressions."""
    before = load_spec(before_path)
    after = load_spec(after_path)

    before_report = analyze(before)
    after_report = analyze(after)

    diff = SchemaDiff(
        score_before=before_report.score,
        score_after=after_report.score,
        token_delta=after.total_tokens - before.total_tokens,
    )

    before_names = {t.name for t in before.tools}
    after_names = {t.name for t in after.tools}

    diff.added_tools = sorted(after_names - before_names)
    diff.removed_tools = sorted(before_names - after_names)

    # Compare common tools
    before_map = {t.name: t for t in before.tools}
    after_map = {t.name: t for t in after.tools}

    for name in sorted(before_names & after_names):
        bt = before_map[name]
        at = after_map[name]
        changes = _diff_tool(bt, at)
        if changes:
            diff.changed_tools.append(ToolDiff(name=name, changes=changes))

    # Identify regressions
    if diff.score_after < diff.score_before:
        diff.regressions.append(
            f"Score dropped: {diff.score_before} → {diff.score_after}"
        )

    if diff.removed_tools:
        diff.regressions.append(
            f"Removed tools: {', '.join(diff.removed_tools)}"
        )

    if diff.token_delta > 200:
        diff.regressions.append(
            f"Token budget increased by {diff.token_delta} tokens"
        )

    # New errors in after that weren't in before
    before_errors = {(i.tool, i.code) for i in before_report.issues}
    after_errors = {(i.tool, i.code) for i in after_report.issues}
    new_errors = after_errors - before_errors
    if new_errors:
        diff.regressions.append(
            f"{len(new_errors)} new schema issues introduced"
        )

    # Improvements
    if diff.score_after > diff.score_before:
        diff.improvements.append(
            f"Score improved: {diff.score_before} → {diff.score_after}"
        )

    fixed_errors = before_errors - after_errors
    if fixed_errors:
        diff.improvements.append(f"{len(fixed_errors)} issues fixed")

    if diff.token_delta < -50:
        diff.improvements.append(f"Saved {-diff.token_delta} tokens")

    return diff


def _diff_tool(before: Tool, after: Tool) -> list[str]:
    changes = []

    if before.description != after.description:
        changes.append("description changed")

    before_params = {p.name for p in before.parameters}
    after_params = {p.name for p in after.parameters}

    added = after_params - before_params
    removed = before_params - after_params

    if added:
        changes.append(f"added params: {', '.join(sorted(added))}")
    if removed:
        changes.append(f"removed params: {', '.join(sorted(removed))}")

    if before.token_estimate != after.token_estimate:
        delta = after.token_estimate - before.token_estimate
        sign = "+" if delta > 0 else ""
        changes.append(f"tokens: {sign}{delta}")

    return changes
