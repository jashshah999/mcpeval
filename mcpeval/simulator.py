"""LLM-powered simulation of tool selection against MCP schemas."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from .schema import MCPServerSpec, Tool


@dataclass
class SimulationCase:
    query: str
    expected_tool: str | None = None
    expected_params: dict[str, Any] | None = None
    category: str = "general"


@dataclass
class SimulationResult:
    case: SimulationCase
    selected_tool: str | None = None
    selected_params: dict[str, Any] | None = None
    correct_tool: bool = False
    correct_params: bool = False
    latency_ms: float = 0
    reasoning: str = ""
    error: str = ""


@dataclass
class SimulationReport:
    results: list[SimulationResult] = field(default_factory=list)
    total_cases: int = 0
    correct_selections: int = 0
    accuracy: float = 0.0
    avg_latency_ms: float = 0.0

    def compute_stats(self) -> None:
        self.total_cases = len(self.results)
        self.correct_selections = sum(1 for r in self.results if r.correct_tool)
        self.accuracy = self.correct_selections / max(self.total_cases, 1)
        latencies = [r.latency_ms for r in self.results if r.latency_ms > 0]
        self.avg_latency_ms = sum(latencies) / max(len(latencies), 1)


def generate_test_cases(spec: MCPServerSpec, count_per_tool: int = 3) -> list[SimulationCase]:
    """Generate test cases from tool schemas (without LLM - rule-based)."""
    cases = []

    for tool in spec.tools:
        # Positive case: query that should trigger this tool
        cases.append(SimulationCase(
            query=_make_positive_query(tool),
            expected_tool=tool.name,
            category="positive",
        ))

        # Edge case: partial/ambiguous query
        if tool.parameters:
            cases.append(SimulationCase(
                query=_make_partial_query(tool),
                expected_tool=tool.name,
                category="partial",
            ))

    # Negative case: query that shouldn't match any tool
    cases.append(SimulationCase(
        query="What is the meaning of life?",
        expected_tool=None,
        category="negative",
    ))
    cases.append(SimulationCase(
        query="Tell me a joke",
        expected_tool=None,
        category="negative",
    ))

    return cases


def _make_positive_query(tool: Tool) -> str:
    """Create a natural language query that should trigger a tool."""
    desc = tool.description or tool.name.replace("_", " ")
    name_parts = tool.name.replace("_", " ").replace("-", " ")

    if tool.parameters:
        param = tool.parameters[0]
        if param.enum:
            return f"{desc} with {param.name} set to {param.enum[0]}"
        return f"I need to {name_parts}"

    return f"Please {name_parts}"


def _make_partial_query(tool: Tool) -> str:
    """Create an ambiguous query that tests tool matching."""
    name_parts = tool.name.replace("_", " ").replace("-", " ").split()
    if len(name_parts) > 1:
        return f"Can you help me with {name_parts[-1]}?"
    return f"Do the {name_parts[0]} thing"


async def run_simulation(
    spec: MCPServerSpec,
    cases: list[SimulationCase],
    provider: str = "gemini",
    model: str | None = None,
    api_key: str | None = None,
) -> SimulationReport:
    """Run simulation cases against an LLM to test tool selection."""
    report = SimulationReport()

    tools_json = _spec_to_tools_json(spec)

    for case in cases:
        t0 = time.time()
        try:
            result = await _simulate_one(case, tools_json, provider, model, api_key)
            result.latency_ms = (time.time() - t0) * 1000

            if case.expected_tool is None:
                result.correct_tool = result.selected_tool is None
            else:
                result.correct_tool = result.selected_tool == case.expected_tool

            if case.expected_params and result.selected_params:
                result.correct_params = all(
                    result.selected_params.get(k) == v
                    for k, v in case.expected_params.items()
                )
            else:
                result.correct_params = True

        except Exception as e:
            result = SimulationResult(case=case, error=str(e))
            result.latency_ms = (time.time() - t0) * 1000

        report.results.append(result)

    report.compute_stats()
    return report


async def _simulate_one(
    case: SimulationCase,
    tools_json: list[dict],
    provider: str,
    model: str | None,
    api_key: str | None,
) -> SimulationResult:
    """Simulate a single tool selection."""
    if provider == "gemini":
        return await _simulate_gemini(case, tools_json, model, api_key)
    elif provider == "openai":
        return await _simulate_openai(case, tools_json, model, api_key)
    elif provider == "anthropic":
        return await _simulate_anthropic(case, tools_json, model, api_key)
    else:
        raise ValueError(f"Unknown provider: {provider}")


async def _simulate_gemini(
    case: SimulationCase,
    tools_json: list[dict],
    model: str | None,
    api_key: str | None,
) -> SimulationResult:
    """Run simulation using Gemini API."""
    from google import genai
    from google.genai import types
    import os

    client = genai.Client(api_key=api_key or os.environ.get("GEMINI_API_KEY"))
    model_id = model or "gemini-2.0-flash"

    # Convert tools to Gemini format
    function_declarations = []
    for tool in tools_json:
        props = {}
        required = []
        schema = tool.get("inputSchema", {})
        for pname, pschema in schema.get("properties", {}).items():
            props[pname] = {
                "type": pschema.get("type", "STRING").upper(),
                "description": pschema.get("description", ""),
            }
            if pschema.get("enum"):
                props[pname]["enum"] = pschema["enum"]
        if schema.get("required"):
            required = schema["required"]

        fd = {
            "name": tool["name"],
            "description": tool.get("description", ""),
            "parameters": {
                "type": "OBJECT",
                "properties": props,
                "required": required,
            } if props else None,
        }
        function_declarations.append(fd)

    tools_config = types.Tool(function_declarations=[
        types.FunctionDeclaration(**fd) for fd in function_declarations
    ])

    response = client.models.generate_content(
        model=model_id,
        contents=case.query,
        config=types.GenerateContentConfig(
            tools=[tools_config],
            tool_config=types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(mode="AUTO")
            ),
        ),
    )

    result = SimulationResult(case=case)

    # Extract tool call from response
    if response.candidates and response.candidates[0].content:
        for part in response.candidates[0].content.parts:
            if part.function_call:
                result.selected_tool = part.function_call.name
                result.selected_params = dict(part.function_call.args) if part.function_call.args else {}
                break
            elif part.text:
                result.reasoning = part.text[:200]

    return result


async def _simulate_openai(
    case: SimulationCase,
    tools_json: list[dict],
    model: str | None,
    api_key: str | None,
) -> SimulationResult:
    """Run simulation using OpenAI API."""
    from openai import AsyncOpenAI
    import os

    client = AsyncOpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY"))
    model_id = model or "gpt-4o-mini"

    # Convert to OpenAI tool format
    openai_tools = []
    for tool in tools_json:
        openai_tools.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("inputSchema", {"type": "object", "properties": {}}),
            }
        })

    response = await client.chat.completions.create(
        model=model_id,
        messages=[{"role": "user", "content": case.query}],
        tools=openai_tools,
        tool_choice="auto",
    )

    result = SimulationResult(case=case)
    msg = response.choices[0].message

    if msg.tool_calls:
        tc = msg.tool_calls[0]
        result.selected_tool = tc.function.name
        try:
            result.selected_params = json.loads(tc.function.arguments)
        except json.JSONDecodeError:
            result.selected_params = {}
    elif msg.content:
        result.reasoning = msg.content[:200]

    return result


async def _simulate_anthropic(
    case: SimulationCase,
    tools_json: list[dict],
    model: str | None,
    api_key: str | None,
) -> SimulationResult:
    """Run simulation using Anthropic API."""
    from anthropic import AsyncAnthropic
    import os

    client = AsyncAnthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))
    model_id = model or "claude-sonnet-4-20250514"

    # Convert to Anthropic tool format
    anthropic_tools = []
    for tool in tools_json:
        anthropic_tools.append({
            "name": tool["name"],
            "description": tool.get("description", ""),
            "input_schema": tool.get("inputSchema", {"type": "object", "properties": {}}),
        })

    response = await client.messages.create(
        model=model_id,
        max_tokens=256,
        messages=[{"role": "user", "content": case.query}],
        tools=anthropic_tools,
    )

    result = SimulationResult(case=case)
    for block in response.content:
        if block.type == "tool_use":
            result.selected_tool = block.name
            result.selected_params = block.input
            break
        elif block.type == "text":
            result.reasoning = block.text[:200]

    return result


def _spec_to_tools_json(spec: MCPServerSpec) -> list[dict]:
    """Convert spec to JSON tool format."""
    tools = []
    for tool in spec.tools:
        tools.append({
            "name": tool.name,
            "description": tool.description,
            "inputSchema": {
                "type": "object",
                "properties": {
                    p.name: {
                        "type": p.type,
                        "description": p.description,
                        **({"enum": p.enum} if p.enum else {}),
                    }
                    for p in tool.parameters
                },
                "required": [p.name for p in tool.parameters if p.required],
            }
        })
    return tools
