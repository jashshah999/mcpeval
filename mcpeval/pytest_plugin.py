"""Pytest plugin for mcpeval - assert MCP schema quality in test suites."""

from __future__ import annotations

from pathlib import Path

import pytest

from .schema import load_spec, MCPServerSpec
from .analyzer import analyze, AnalysisReport


def pytest_addoption(parser):
    group = parser.getgroup("mcpeval")
    group.addoption(
        "--mcpeval-schema",
        action="store",
        default=None,
        help="Path to MCP schema file to test",
    )
    group.addoption(
        "--mcpeval-min-score",
        action="store",
        default=80,
        type=int,
        help="Minimum passing score (default: 80)",
    )


@pytest.fixture
def mcp_schema(request) -> MCPServerSpec:
    """Load an MCP schema for testing."""
    schema_path = request.config.getoption("--mcpeval-schema")
    if schema_path:
        return load_spec(Path(schema_path))
    # Try to find a schema file in common locations
    for candidate in ["mcpeval.json", "mcp_tools.json", "tools.json", "schema.json"]:
        p = Path(candidate)
        if p.exists():
            return load_spec(p)
    pytest.skip("No MCP schema file found. Use --mcpeval-schema or create mcpeval.json")


@pytest.fixture
def mcp_report(mcp_schema) -> AnalysisReport:
    """Run mcpeval analysis and return the report."""
    return analyze(mcp_schema)


@pytest.fixture
def mcp_score(mcp_report) -> int:
    """Get the mcpeval score."""
    return mcp_report.score


@pytest.fixture
def assert_mcp_quality():
    """Assert schema quality on a specific file."""
    def _assert(schema_path: str | Path, min_score: int = 80, no_errors: bool = True):
        spec = load_spec(Path(schema_path))
        report = analyze(spec)

        if no_errors and report.error_count > 0:
            error_msgs = [f"  - [{i.tool}] {i.message}" for i in report.issues if i.severity.value == "error"]
            pytest.fail(
                f"MCP schema has {report.error_count} errors:\n" + "\n".join(error_msgs)
            )

        if report.score < min_score:
            pytest.fail(
                f"MCP schema score {report.score} is below minimum {min_score}. "
                f"Run 'mcpeval check {schema_path}' for details."
            )

        return report

    return _assert
