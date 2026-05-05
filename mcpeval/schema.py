"""MCP schema parsing and analysis."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ToolParam:
    name: str
    type: str
    description: str = ""
    required: bool = False
    enum: list[str] = field(default_factory=list)


@dataclass
class Tool:
    name: str
    description: str = ""
    parameters: list[ToolParam] = field(default_factory=list)
    raw_schema: dict = field(default_factory=dict)

    @property
    def token_estimate(self) -> int:
        text = json.dumps(self.raw_schema)
        return len(text) // 4

    @property
    def param_count(self) -> int:
        return len(self.parameters)


@dataclass
class MCPServerSpec:
    name: str
    tools: list[Tool] = field(default_factory=list)
    source: str = ""

    @property
    def total_tokens(self) -> int:
        return sum(t.token_estimate for t in self.tools)


def parse_mcp_config(path: Path) -> MCPServerSpec:
    """Parse an MCP server config file (JSON with tools array)."""
    data = json.loads(path.read_text())

    if "tools" in data:
        tools_data = data["tools"]
        name = data.get("name", path.stem)
    elif isinstance(data, list):
        tools_data = data
        name = path.stem
    else:
        raise ValueError(f"Cannot parse MCP config: {path}")

    tools = []
    for td in tools_data:
        params = _extract_params(td)
        tools.append(Tool(
            name=td.get("name", "unknown"),
            description=td.get("description", ""),
            parameters=params,
            raw_schema=td,
        ))

    return MCPServerSpec(name=name, tools=tools, source=str(path))


def parse_openapi_spec(path: Path) -> MCPServerSpec:
    """Parse an OpenAPI spec and extract as MCP tools."""
    import yaml
    data = yaml.safe_load(path.read_text())

    name = data.get("info", {}).get("title", path.stem)
    tools = []

    paths = data.get("paths", {})
    for endpoint, methods in paths.items():
        for method, spec in methods.items():
            if method in ("get", "post", "put", "delete", "patch"):
                tool_name = spec.get("operationId", f"{method}_{endpoint.replace('/', '_').strip('_')}")
                desc = spec.get("summary", spec.get("description", ""))

                params = []
                for p in spec.get("parameters", []):
                    params.append(ToolParam(
                        name=p.get("name", ""),
                        type=p.get("schema", {}).get("type", "string"),
                        description=p.get("description", ""),
                        required=p.get("required", False),
                    ))

                body = spec.get("requestBody", {})
                if body:
                    content = body.get("content", {})
                    json_schema = content.get("application/json", {}).get("schema", {})
                    props = json_schema.get("properties", {})
                    required_fields = json_schema.get("required", [])
                    for pname, pschema in props.items():
                        params.append(ToolParam(
                            name=pname,
                            type=pschema.get("type", "object"),
                            description=pschema.get("description", ""),
                            required=pname in required_fields,
                        ))

                raw = {
                    "name": tool_name,
                    "description": desc,
                    "inputSchema": {
                        "type": "object",
                        "properties": {p.name: {"type": p.type, "description": p.description} for p in params},
                        "required": [p.name for p in params if p.required],
                    }
                }
                tools.append(Tool(name=tool_name, description=desc, parameters=params, raw_schema=raw))

    return MCPServerSpec(name=name, tools=tools, source=str(path))


def _extract_params(tool_data: dict) -> list[ToolParam]:
    schema = tool_data.get("inputSchema", tool_data.get("parameters", {}))
    if not schema:
        return []

    props = schema.get("properties", {})
    required = schema.get("required", [])
    params = []

    for pname, pschema in props.items():
        params.append(ToolParam(
            name=pname,
            type=pschema.get("type", "string"),
            description=pschema.get("description", ""),
            required=pname in required,
            enum=pschema.get("enum", []),
        ))

    return params


def load_spec(path: Path) -> MCPServerSpec:
    """Auto-detect and load a spec file."""
    text = path.read_text()
    if path.suffix in (".yaml", ".yml"):
        return parse_openapi_spec(path)
    try:
        data = json.loads(text)
        if "openapi" in data:
            return parse_openapi_spec(path)
        return parse_mcp_config(path)
    except json.JSONDecodeError:
        return parse_openapi_spec(path)
