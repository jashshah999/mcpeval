"""Auto-fix common schema issues without needing an LLM."""

from __future__ import annotations

import json
import copy
from pathlib import Path

from .schema import MCPServerSpec
from .analyzer import analyze


def auto_fix(spec: MCPServerSpec) -> tuple[MCPServerSpec, list[str]]:
    """Apply automatic fixes to schema issues. Returns fixed spec and list of changes."""
    report = analyze(spec)
    changes = []

    fixed_tools = []
    for tool in spec.tools:
        fixed = copy.deepcopy(tool)
        tool_issues = [i for i in report.issues if i.tool == tool.name]

        for issue in tool_issues:
            if issue.code == "REDUNDANT_PREFIX":
                prefixes = ("do_", "perform_", "execute_", "run_")
                for p in prefixes:
                    if fixed.name.startswith(p):
                        old_name = fixed.name
                        fixed.name = fixed.name[len(p):]
                        fixed.raw_schema["name"] = fixed.name
                        changes.append(f"Renamed '{old_name}' → '{fixed.name}'")
                        break

            elif issue.code == "SPACE_IN_NAME":
                old_name = fixed.name
                fixed.name = fixed.name.replace(" ", "_")
                fixed.raw_schema["name"] = fixed.name
                changes.append(f"Fixed spaces in '{old_name}' → '{fixed.name}'")

            elif issue.code == "NO_DESCRIPTION" and not fixed.description:
                desc = _infer_description(fixed.name)
                fixed.description = desc
                fixed.raw_schema["description"] = desc
                changes.append(f"Added inferred description to '{fixed.name}'")

        fixed_tools.append(fixed)

    fixed_spec = MCPServerSpec(
        name=spec.name,
        tools=fixed_tools,
        source=spec.source,
    )
    return fixed_spec, changes


def _infer_description(name: str) -> str:
    """Infer a basic description from tool name."""
    parts = name.replace("-", "_").split("_")
    verb = parts[0].capitalize() if parts else "Perform"
    noun = " ".join(parts[1:]) if len(parts) > 1 else "operation"
    return f"{verb} {noun}"


def export_fixed(spec: MCPServerSpec, output_path: Path) -> None:
    """Export fixed spec to a JSON file."""
    data = {
        "name": spec.name,
        "tools": [t.raw_schema for t in spec.tools],
    }
    output_path.write_text(json.dumps(data, indent=2))
