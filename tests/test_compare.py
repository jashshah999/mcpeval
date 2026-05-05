"""Tests for schema comparison."""

import json
import tempfile
from pathlib import Path

from mcpeval.compare import compare_specs


def _write_spec(tools, name="test"):
    data = {"name": name, "tools": tools}
    f = tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False)
    json.dump(data, f)
    f.flush()
    f.close()
    return Path(f.name)


def test_added_tool_detected():
    before = _write_spec([
        {"name": "search", "description": "Search for items by keyword", "inputSchema": {"type": "object", "properties": {}}},
    ])
    after = _write_spec([
        {"name": "search", "description": "Search for items by keyword", "inputSchema": {"type": "object", "properties": {}}},
        {"name": "delete", "description": "Delete an item permanently from the database", "inputSchema": {"type": "object", "properties": {}}},
    ])
    diff = compare_specs(before, after)
    assert "delete" in diff.added_tools
    assert not diff.removed_tools


def test_removed_tool_is_regression():
    before = _write_spec([
        {"name": "search", "description": "Search for items by keyword", "inputSchema": {"type": "object", "properties": {}}},
        {"name": "delete", "description": "Delete an item permanently from the database", "inputSchema": {"type": "object", "properties": {}}},
    ])
    after = _write_spec([
        {"name": "search", "description": "Search for items by keyword", "inputSchema": {"type": "object", "properties": {}}},
    ])
    diff = compare_specs(before, after)
    assert "delete" in diff.removed_tools
    assert diff.has_regressions


def test_score_improvement_detected():
    before = _write_spec([
        {"name": "search_items", "description": "short", "inputSchema": {"type": "object", "properties": {"data": {"type": "string"}}}},
    ])
    after = _write_spec([
        {"name": "search_items", "description": "Search for items in the database by keyword query", "inputSchema": {"type": "object", "properties": {"query": {"type": "string", "description": "Search term"}}, "required": ["query"]}},
    ])
    diff = compare_specs(before, after)
    assert diff.score_after > diff.score_before
    assert not diff.has_regressions


def test_param_changes_detected():
    before = _write_spec([
        {"name": "search", "description": "Search for items by keyword", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}}},
    ])
    after = _write_spec([
        {"name": "search", "description": "Search for items by keyword", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}}}},
    ])
    diff = compare_specs(before, after)
    assert len(diff.changed_tools) == 1
    assert "added params: limit" in diff.changed_tools[0].changes[0]
