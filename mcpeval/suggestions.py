"""AI-powered schema improvement suggestions."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from .schema import MCPServerSpec, Tool


@dataclass
class Suggestion:
    tool: str
    category: str
    original: str
    improved: str
    reason: str


async def suggest_improvements(
    spec: MCPServerSpec,
    provider: str = "gemini",
    api_key: str | None = None,
) -> list[Suggestion]:
    """Use LLM to suggest schema improvements."""
    tools_json = json.dumps([t.raw_schema for t in spec.tools], indent=2)

    prompt = f"""You are an expert at writing MCP (Model Context Protocol) tool schemas that work well with LLMs.

Analyze these tool definitions and suggest improvements. Focus on:
1. Description clarity - will an LLM know WHEN to use each tool?
2. Parameter naming - are names self-explanatory?
3. Missing information - what would help the LLM make better decisions?
4. Disambiguation - if there are similar tools, how to differentiate?

Tool schemas:
{tools_json}

For each issue found, respond in this exact JSON format (array of objects):
[
  {{
    "tool": "tool_name",
    "category": "description|naming|params|disambiguation",
    "original": "the problematic text",
    "improved": "your suggested replacement",
    "reason": "why this helps LLMs"
  }}
]

Return ONLY the JSON array. If no improvements needed, return [].
"""

    if provider == "gemini":
        return await _suggest_gemini(prompt, api_key)
    elif provider == "openai":
        return await _suggest_openai(prompt, api_key)
    else:
        return []


async def _suggest_gemini(prompt: str, api_key: str | None) -> list[Suggestion]:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key or os.environ.get("GEMINI_API_KEY"))

    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
        ),
    )

    try:
        data = json.loads(response.text)
        return [Suggestion(**item) for item in data]
    except (json.JSONDecodeError, TypeError, KeyError):
        return []


async def _suggest_openai(prompt: str, api_key: str | None) -> list[Suggestion]:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY"))

    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
    )

    try:
        data = json.loads(response.choices[0].message.content)
        if isinstance(data, list):
            return [Suggestion(**item) for item in data]
        elif "suggestions" in data:
            return [Suggestion(**item) for item in data["suggestions"]]
        return []
    except (json.JSONDecodeError, TypeError, KeyError):
        return []
