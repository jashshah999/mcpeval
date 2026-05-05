"""Tests for static analyzer."""

import json
import tempfile
from pathlib import Path

from mcpeval.schema import load_spec
from mcpeval.analyzer import analyze, Severity


def _make_spec(tools):
    data = {"name": "test", "tools": tools}
    with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
        json.dump(data, f)
        f.flush()
        return load_spec(Path(f.name))


def test_no_description_error():
    spec = _make_spec([{"name": "my_tool", "inputSchema": {"type": "object", "properties": {}}}])
    report = analyze(spec)
    errors = [i for i in report.issues if i.code == "NO_DESCRIPTION"]
    assert len(errors) == 1
    assert errors[0].severity == Severity.ERROR


def test_short_description_warning():
    spec = _make_spec([{"name": "my_tool", "description": "Does stuff", "inputSchema": {"type": "object", "properties": {}}}])
    report = analyze(spec)
    warnings = [i for i in report.issues if i.code == "SHORT_DESCRIPTION"]
    assert len(warnings) == 1


def test_space_in_name():
    spec = _make_spec([{"name": "my tool", "description": "Search for things in the database", "inputSchema": {"type": "object", "properties": {}}}])
    report = analyze(spec)
    errors = [i for i in report.issues if i.code == "SPACE_IN_NAME"]
    assert len(errors) == 1


def test_too_many_params():
    props = {f"param_{i}": {"type": "string"} for i in range(12)}
    spec = _make_spec([{
        "name": "big_tool",
        "description": "A tool with way too many parameters for LLMs to handle properly",
        "inputSchema": {"type": "object", "properties": props},
    }])
    report = analyze(spec)
    warnings = [i for i in report.issues if i.code == "TOO_MANY_PARAMS"]
    assert len(warnings) == 1


def test_ambiguous_param():
    spec = _make_spec([{
        "name": "my_tool",
        "description": "Search for documents in the knowledge base by query",
        "inputSchema": {
            "type": "object",
            "properties": {
                "data": {"type": "string"},
            },
        },
    }])
    report = analyze(spec)
    warnings = [i for i in report.issues if i.code == "AMBIGUOUS_PARAM"]
    assert len(warnings) == 1


def test_redundant_prefix():
    spec = _make_spec([{
        "name": "do_search",
        "description": "Search for items in the database by keyword query",
        "inputSchema": {"type": "object", "properties": {}},
    }])
    report = analyze(spec)
    infos = [i for i in report.issues if i.code == "REDUNDANT_PREFIX"]
    assert len(infos) == 1


def test_similar_tools():
    spec = _make_spec([
        {"name": "search_users", "description": "Search for users by name or email in the database", "inputSchema": {"type": "object", "properties": {}}},
        {"name": "find_users", "description": "Search for users by name or email in the database", "inputSchema": {"type": "object", "properties": {}}},
    ])
    report = analyze(spec)
    warnings = [i for i in report.issues if i.code == "SIMILAR_TOOLS"]
    assert len(warnings) == 1


def test_good_schema_high_score():
    spec = _make_spec([{
        "name": "search_documents",
        "description": "Search for documents by keyword query. Returns matching titles and snippets.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search term to match against document content"},
                "limit": {"type": "integer", "description": "Maximum results to return (default: 10)"},
            },
            "required": ["query"],
        },
    }])
    report = analyze(spec)
    assert report.score >= 80
    assert report.passed


def test_missing_enum():
    spec = _make_spec([{
        "name": "update_record",
        "description": "Update a record's status in the system to track progress",
        "inputSchema": {
            "type": "object",
            "properties": {
                "status": {"type": "string"},
            },
        },
    }])
    report = analyze(spec)
    warnings = [i for i in report.issues if i.code == "MISSING_ENUM"]
    assert len(warnings) == 1


def test_score_deductions():
    spec = _make_spec([
        {"name": "do_search", "inputSchema": {"type": "object", "properties": {"data": {"type": "string"}}}},
    ])
    report = analyze(spec)
    assert report.score < 80
    assert not report.passed
