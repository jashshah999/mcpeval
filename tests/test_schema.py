"""Tests for schema parsing."""

import json
import tempfile
from pathlib import Path

from mcpeval.schema import parse_mcp_config, load_spec, MCPServerSpec


def test_parse_mcp_config():
    data = {
        "name": "test-server",
        "tools": [
            {
                "name": "search",
                "description": "Search for items",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "limit": {"type": "integer"},
                    },
                    "required": ["query"],
                },
            }
        ],
    }

    with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
        json.dump(data, f)
        f.flush()
        spec = parse_mcp_config(Path(f.name))

    assert spec.name == "test-server"
    assert len(spec.tools) == 1
    assert spec.tools[0].name == "search"
    assert len(spec.tools[0].parameters) == 2
    assert spec.tools[0].parameters[0].required is True
    assert spec.tools[0].parameters[1].required is False


def test_parse_tools_array():
    data = [
        {"name": "tool1", "description": "First tool", "inputSchema": {"type": "object", "properties": {}}},
        {"name": "tool2", "description": "Second tool", "inputSchema": {"type": "object", "properties": {}}},
    ]

    with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
        json.dump(data, f)
        f.flush()
        spec = parse_mcp_config(Path(f.name))

    assert len(spec.tools) == 2


def test_token_estimate():
    data = {
        "name": "test",
        "tools": [
            {
                "name": "big_tool",
                "description": "A tool with a very long description " * 10,
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "a": {"type": "string"},
                        "b": {"type": "string"},
                        "c": {"type": "string"},
                    },
                },
            }
        ],
    }

    with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
        json.dump(data, f)
        f.flush()
        spec = load_spec(Path(f.name))

    assert spec.total_tokens > 0
    assert spec.tools[0].token_estimate > 50


def test_load_spec_openapi():
    openapi = """
openapi: "3.0.0"
info:
  title: Test API
  version: "1.0"
paths:
  /users:
    get:
      operationId: list_users
      summary: List all users
      parameters:
        - name: page
          in: query
          schema:
            type: integer
          description: Page number
"""
    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        f.write(openapi)
        f.flush()
        spec = load_spec(Path(f.name))

    assert spec.name == "Test API"
    assert len(spec.tools) == 1
    assert spec.tools[0].name == "list_users"
