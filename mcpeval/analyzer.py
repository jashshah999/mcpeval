"""Static analysis of MCP tool schemas - catches issues without needing an LLM."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .schema import MCPServerSpec, Tool, ToolParam


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class Issue:
    tool: str
    severity: Severity
    code: str
    message: str
    suggestion: str = ""


@dataclass
class AnalysisReport:
    spec: MCPServerSpec
    issues: list[Issue] = field(default_factory=list)
    score: int = 100  # starts at 100, deductions for issues

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == Severity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == Severity.WARNING)

    @property
    def passed(self) -> bool:
        return self.error_count == 0


def analyze(spec: MCPServerSpec) -> AnalysisReport:
    """Run all static checks on an MCP server spec."""
    report = AnalysisReport(spec=spec)

    for tool in spec.tools:
        _check_description(tool, report)
        _check_naming(tool, report)
        _check_params(tool, report)
        _check_token_budget(tool, report)
        _check_ambiguity(tool, spec, report)

    _check_overlap(spec, report)

    # Calculate score
    for issue in report.issues:
        if issue.severity == Severity.ERROR:
            report.score -= 15
        elif issue.severity == Severity.WARNING:
            report.score -= 5
        else:
            report.score -= 1
    report.score = max(0, report.score)

    return report


def _check_description(tool: Tool, report: AnalysisReport) -> None:
    if not tool.description:
        report.issues.append(Issue(
            tool=tool.name,
            severity=Severity.ERROR,
            code="NO_DESCRIPTION",
            message="Tool has no description. LLMs cannot understand when to use it.",
            suggestion="Add a clear description explaining what this tool does and when to use it.",
        ))
        return

    if len(tool.description) < 20:
        report.issues.append(Issue(
            tool=tool.name,
            severity=Severity.WARNING,
            code="SHORT_DESCRIPTION",
            message=f"Description is only {len(tool.description)} chars. LLMs need more context.",
            suggestion="Expand description to explain: what it does, when to use it, what it returns.",
        ))

    if len(tool.description) > 500:
        report.issues.append(Issue(
            tool=tool.name,
            severity=Severity.WARNING,
            code="LONG_DESCRIPTION",
            message=f"Description is {len(tool.description)} chars. This wastes context window tokens.",
            suggestion="Trim to under 200 chars. Move examples to parameter descriptions instead.",
        ))

    # Check for action verbs
    first_word = tool.description.strip().split()[0].lower() if tool.description.strip() else ""
    action_verbs = {"get", "fetch", "create", "update", "delete", "search", "list", "send",
                    "retrieve", "find", "add", "remove", "set", "check", "validate", "compute",
                    "calculate", "generate", "convert", "parse", "extract", "submit", "query"}
    if first_word not in action_verbs and not first_word.endswith("s"):
        report.issues.append(Issue(
            tool=tool.name,
            severity=Severity.INFO,
            code="NO_ACTION_VERB",
            message="Description doesn't start with an action verb.",
            suggestion=f"Start with a verb like 'Get', 'Create', 'Search'. Currently starts with '{first_word}'.",
        ))


def _check_naming(tool: Tool, report: AnalysisReport) -> None:
    name = tool.name

    if " " in name:
        report.issues.append(Issue(
            tool=name,
            severity=Severity.ERROR,
            code="SPACE_IN_NAME",
            message="Tool name contains spaces. This will break most MCP clients.",
            suggestion="Use snake_case or camelCase instead.",
        ))

    if len(name) > 64:
        report.issues.append(Issue(
            tool=name,
            severity=Severity.WARNING,
            code="LONG_NAME",
            message=f"Tool name is {len(name)} chars. LLMs may truncate or confuse it.",
            suggestion="Keep tool names under 40 characters.",
        ))

    if name.startswith(("do_", "perform_", "execute_", "run_")):
        report.issues.append(Issue(
            tool=name,
            severity=Severity.INFO,
            code="REDUNDANT_PREFIX",
            message=f"Prefix '{name.split('_')[0]}_' is redundant — all tools perform actions.",
            suggestion=f"Rename to '{name.split('_', 1)[1]}' for clarity.",
        ))


def _check_params(tool: Tool, report: AnalysisReport) -> None:
    if tool.param_count > 10:
        report.issues.append(Issue(
            tool=tool.name,
            severity=Severity.WARNING,
            code="TOO_MANY_PARAMS",
            message=f"Tool has {tool.param_count} parameters. LLMs struggle with >5 params.",
            suggestion="Group related params into a nested object, or split into multiple tools.",
        ))

    for param in tool.parameters:
        if not param.description:
            report.issues.append(Issue(
                tool=tool.name,
                severity=Severity.WARNING,
                code="PARAM_NO_DESC",
                message=f"Parameter '{param.name}' has no description.",
                suggestion=f"Add description for '{param.name}' explaining expected format and purpose.",
            ))

        if param.type == "string" and not param.enum and param.name in (
            "format", "type", "mode", "status", "action", "method"
        ):
            report.issues.append(Issue(
                tool=tool.name,
                severity=Severity.WARNING,
                code="MISSING_ENUM",
                message=f"Parameter '{param.name}' looks like it should have enum values.",
                suggestion=f"Add enum values to '{param.name}' so LLMs know valid options.",
            ))

        # Check for ambiguous param names
        ambiguous = {"data", "value", "input", "output", "info", "item", "thing", "stuff", "obj"}
        if param.name.lower() in ambiguous:
            report.issues.append(Issue(
                tool=tool.name,
                severity=Severity.WARNING,
                code="AMBIGUOUS_PARAM",
                message=f"Parameter '{param.name}' is too generic. LLMs won't know what to pass.",
                suggestion=f"Rename '{param.name}' to something specific like 'user_email' or 'search_query'.",
            ))


def _check_token_budget(tool: Tool, report: AnalysisReport) -> None:
    tokens = tool.token_estimate
    if tokens > 1000:
        report.issues.append(Issue(
            tool=tool.name,
            severity=Severity.WARNING,
            code="TOKEN_HOG",
            message=f"Tool schema uses ~{tokens} tokens. This eats into the context window.",
            suggestion="Simplify schema. Remove redundant descriptions. Consider splitting into smaller tools.",
        ))


def _check_ambiguity(tool: Tool, spec: MCPServerSpec, report: AnalysisReport) -> None:
    # Check if tool name contains its domain (helps LLM disambiguation)
    if len(spec.tools) > 5:
        parts = tool.name.replace("-", "_").split("_")
        if len(parts) == 1 and tool.name in ("search", "get", "list", "create", "update", "delete"):
            report.issues.append(Issue(
                tool=tool.name,
                severity=Severity.WARNING,
                code="GENERIC_NAME",
                message=f"Tool name '{tool.name}' is too generic in a server with {len(spec.tools)} tools.",
                suggestion="Prefix with domain: 'search_users', 'list_orders', etc.",
            ))


def _check_overlap(spec: MCPServerSpec, report: AnalysisReport) -> None:
    """Check for tools with overlapping descriptions that could confuse LLMs."""
    from difflib import SequenceMatcher

    tools = spec.tools
    for i in range(len(tools)):
        for j in range(i + 1, len(tools)):
            if not tools[i].description or not tools[j].description:
                continue
            ratio = SequenceMatcher(None, tools[i].description.lower(), tools[j].description.lower()).ratio()
            if ratio > 0.7:
                report.issues.append(Issue(
                    tool=tools[i].name,
                    severity=Severity.WARNING,
                    code="SIMILAR_TOOLS",
                    message=f"'{tools[i].name}' and '{tools[j].name}' have {int(ratio*100)}% similar descriptions.",
                    suggestion="Differentiate descriptions clearly so LLMs know which to pick.",
                ))
