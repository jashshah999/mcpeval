# mcpeval

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-17%20passed-green.svg)]()

**Lint, test, and optimize your MCP tool schemas before shipping.**

You built an MCP server. But will Claude/GPT actually use your tools correctly? `mcpeval` tells you before your users find out.

```
$ mcpeval check my_server.json

  Schema Score: 34/100 (F)
  Errors: 3  Warnings: 12

  ✗  perform_delete    Tool has no description. LLMs cannot understand when to use it.
  !  do_search         Parameter 'data' is too generic. LLMs won't know what to pass.
  !  update_record     Parameter 'status' looks like it should have enum values.
  !  search/find       'search_users' and 'find_users' have 89% similar descriptions.
```

## Why?

Building MCP servers is easy. Building MCP servers that **LLMs actually use correctly** is hard:

- **Ambiguous descriptions** → LLM picks the wrong tool
- **Generic param names** (`data`, `value`, `input`) → LLM passes garbage
- **Missing enums** → LLM invents invalid values
- **Similar tools** → LLM can't distinguish between them
- **Schema bloat** → wastes 40% of your context window

You find these bugs in production, from user complaints. `mcpeval` catches them in CI.

## Install

```bash
pip install mcpeval
```

For LLM simulation (optional):
```bash
pip install mcpeval[gemini]    # uses Gemini Flash (cheapest)
pip install mcpeval[openai]    # uses GPT-4o-mini
pip install mcpeval[anthropic] # uses Claude Sonnet
```

## Quick Start

### 1. Check your schema (no API key needed)

```bash
# From MCP tools JSON
mcpeval check my_server.json

# From OpenAPI spec
mcpeval check api_spec.yaml

# Generate a sample to try
mcpeval init
mcpeval check mcpeval.json
```

### 2. Simulate LLM tool selection

```bash
# Test if an LLM actually picks the right tool for natural language queries
mcpeval check my_server.json --simulate --provider gemini

  Simulation Results
  Accuracy: 75% (6/8)

  ✓  "Find users named John"        → search_users     ✓
  ✗  "Remove the old account"       → delete_user      ✗ (got: deactivate_user)
  ✓  "Update email to new@test.com" → update_user      ✓
```

### 3. Get AI-powered fix suggestions

```bash
mcpeval check my_server.json --suggest

  AI Suggestions

  1. do_search (naming)
     - do_search
     + search_customers
     Prefix 'do_' is redundant and the noun clarifies what's being searched.

  2. perform_delete (description)
     - (empty)
     + Permanently delete a customer record by ID. Cannot be undone.
     LLMs need clear descriptions to know when to select a tool.
```

### 4. Use in CI

```bash
# Exit code 1 on errors (blocks PR)
mcpeval check my_server.json --ci

# JSON output for programmatic use
mcpeval check my_server.json --json-output
```

### 5. Token budget analysis

```bash
mcpeval tokens my_server.json

  Token Budget
  Tool                    Tokens   % Budget
  update_customer_info…      196       50%   ████████████░░░░░░░
  search_customers            77       20%   ████░░░░░░░░░░░░░░░
  get                         40       10%   ██░░░░░░░░░░░░░░░░░
  Total                      393      100%
```

## What It Checks

### Static Analysis (free, instant)

| Check | What it catches |
|-------|----------------|
| `NO_DESCRIPTION` | Tool has no description — LLM can't know when to use it |
| `SHORT_DESCRIPTION` | Description too brief for LLM to understand |
| `LONG_DESCRIPTION` | Description wastes context tokens |
| `SPACE_IN_NAME` | Spaces break MCP clients |
| `LONG_NAME` | Names >64 chars confuse LLMs |
| `REDUNDANT_PREFIX` | `do_`, `perform_`, `execute_` prefixes add nothing |
| `TOO_MANY_PARAMS` | >10 params — LLMs struggle with complex inputs |
| `PARAM_NO_DESC` | Parameter has no description |
| `MISSING_ENUM` | Looks like it needs enum values (status, type, mode) |
| `AMBIGUOUS_PARAM` | Generic names: `data`, `value`, `input`, `item` |
| `SIMILAR_TOOLS` | Two tools with >70% similar descriptions |
| `TOKEN_HOG` | Single tool uses >1000 tokens |
| `GENERIC_NAME` | Tool named `search` or `get` in a server with 5+ tools |

### LLM Simulation (requires API key)

- Sends natural language queries to the LLM with your tool schemas
- Measures: does it pick the right tool? Pass the right args?
- Tests positive cases (should trigger tool) and negative cases (should not)
- Reports accuracy score and identifies failure cases

## Input Formats

mcpeval accepts:

**MCP Tools JSON** (most common):
```json
{
  "name": "my-server",
  "tools": [
    {
      "name": "search_docs",
      "description": "Search documents by query",
      "inputSchema": {
        "type": "object",
        "properties": {
          "query": { "type": "string", "description": "Search term" }
        },
        "required": ["query"]
      }
    }
  ]
}
```

**OpenAPI/Swagger spec** (YAML or JSON):
```bash
mcpeval check openapi.yaml
```

**Custom test cases** (for simulation):
```yaml
# tests.yaml
- query: "Find all active users"
  expected_tool: search_users
- query: "What's the weather?"
  expected_tool: null  # should NOT trigger any tool
```

```bash
mcpeval check server.json --simulate --cases tests.yaml
```

## pytest Integration

```python
# test_my_mcp_server.py

def test_schema_quality(assert_mcp_quality):
    """Fail if schema score drops below 80 or has errors."""
    assert_mcp_quality("mcp_tools.json", min_score=80)

def test_no_token_bloat(mcp_schema):
    """Ensure total schema tokens stay reasonable."""
    assert mcp_schema.total_tokens < 2000

def test_all_tools_documented(mcp_schema):
    """Every tool must have a description."""
    for tool in mcp_schema.tools:
        assert tool.description, f"{tool.name} has no description"
```

```bash
pytest --mcpeval-schema mcp_tools.json
```

## GitHub Action

```yaml
name: MCP Schema Check
on: [push, pull_request]
jobs:
  mcpeval:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install mcpeval
      - run: mcpeval check mcp_tools.json --ci
```

Automatically posts a schema report as a PR comment when schema files change (see `.github/workflows/pr-comment.yml`).

## Schema Diffing (catch regressions)

```bash
# Compare before/after and block CI on regressions
mcpeval diff schema_v1.json schema_v2.json --ci

  Schema Diff: schema_v1.json → schema_v2.json
  Score: 72 → 45 (-27)
  Tokens: +340
  - Removed: get_user
  ~ search: description changed; added params: filter; tokens: +85

  Regressions:
    ✗ Score dropped: 72 → 45
    ✗ Removed tools: get_user
    ✗ 3 new schema issues introduced
```

### Watch mode (live development)

```bash
# Re-runs analysis every time you save the file
mcpeval watch my_server.json
```

### PR comment reports

```bash
# Generate markdown for PR comments
mcpeval report my_server.json -f markdown -o report.md

# Get a badge URL
mcpeval report my_server.json -f badge
# → https://img.shields.io/badge/mcpeval-85%2F100%20(B)-brightgreen
```

### Auto-fix

```bash
# Fix common issues automatically (renames, adds inferred descriptions)
mcpeval fix my_server.json
  → Renamed 'do_search' → 'search'
  → Renamed 'perform_delete' → 'delete'
  → Added inferred description to 'delete'
```

### Connect to live MCP servers

```bash
# Analyze a running MCP server directly via stdio
mcpeval connect npx -y @modelcontextprotocol/server-filesystem /tmp
```

## CLI Reference

```
mcpeval check <spec>       Analyze schema (add --simulate, --suggest, --ci)
mcpeval diff <v1> <v2>     Compare versions, detect regressions
mcpeval fix <spec>         Auto-fix common issues
mcpeval watch <spec>       Live re-analysis on file changes
mcpeval report <spec>      Generate markdown/badge reports
mcpeval tokens <spec>      Show token usage breakdown
mcpeval improve <spec>     Get AI suggestions (requires API key)
mcpeval gen <spec>         Generate test cases from schema
mcpeval connect <cmd...>   Connect to live MCP server via stdio
mcpeval init               Create sample mcpeval.json
```

## Why Not Just Use the MCP Inspector?

The [MCP Inspector](https://github.com/modelcontextprotocol/inspector) (9.6k stars) is for **manual visual testing** — you send requests and look at responses.

mcpeval is for **automated quality assurance**:
- Catches schema anti-patterns without running your server
- Simulates how LLMs will interpret your schemas
- Runs in CI to prevent regressions
- Gives a score and actionable fixes

They're complementary: Inspector for debugging, mcpeval for quality gates.

## License

MIT
