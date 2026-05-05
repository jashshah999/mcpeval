"""Tests for simulation test case generation."""

import json
import tempfile
from pathlib import Path

from mcpeval.schema import load_spec
from mcpeval.simulator import generate_test_cases


def _make_spec(tools):
    data = {"name": "test", "tools": tools}
    with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
        json.dump(data, f)
        f.flush()
        return load_spec(Path(f.name))


def test_generates_positive_cases():
    spec = _make_spec([
        {"name": "search", "description": "Search items", "inputSchema": {"type": "object", "properties": {"q": {"type": "string"}}}},
        {"name": "delete", "description": "Delete items", "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}}}},
    ])
    cases = generate_test_cases(spec)
    positive = [c for c in cases if c.category == "positive"]
    assert len(positive) == 2
    assert positive[0].expected_tool == "search"
    assert positive[1].expected_tool == "delete"


def test_generates_negative_cases():
    spec = _make_spec([
        {"name": "search", "description": "Search items", "inputSchema": {"type": "object", "properties": {}}},
    ])
    cases = generate_test_cases(spec)
    negative = [c for c in cases if c.category == "negative"]
    assert len(negative) >= 1
    assert all(c.expected_tool is None for c in negative)


def test_generates_partial_cases():
    spec = _make_spec([
        {"name": "search_flights", "description": "Search flights", "inputSchema": {
            "type": "object",
            "properties": {"dest": {"type": "string", "description": "Destination"}},
            "required": ["dest"],
        }},
    ])
    cases = generate_test_cases(spec)
    partial = [c for c in cases if c.category == "partial"]
    assert len(partial) >= 1
