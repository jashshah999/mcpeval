# Marketing Copy

## Reddit Post (r/ChatGPTCoding, r/ClaudeAI, r/LocalLLaMA)

**Title:** I built a linter for MCP tool schemas — catches the bugs that make Claude pick the wrong tool

**Body:**

I've been building MCP servers and kept hitting the same issue: Claude or GPT would pick the wrong tool, or pass garbage arguments. After debugging for hours I realized the problem was always in my schemas — ambiguous descriptions, generic param names like "data", missing enums.

So I built **mcpeval** — a CLI that statically analyzes your MCP tool schemas and tells you exactly what's wrong:

```
$ mcpeval check my_server.json

  Schema Score: 34/100 (F)
  ✗  perform_delete    Tool has no description. LLMs cannot understand when to use it.
  !  do_search         Parameter 'data' is too generic. LLMs won't know what to pass.
  !  update_record     Parameter 'status' looks like it should have enum values.
```

It checks 13 anti-patterns that confuse LLMs, shows token budget breakdown (how much context window each tool eats), and can run in CI to block PRs that regress schema quality.

Optional: LLM simulation mode that actually tests whether a model picks the right tool for natural language queries.

No API key needed for the core linter. `pip install mcpeval && mcpeval check your_schema.json`

GitHub: https://github.com/jashshah999/mcpeval

---

## HN Post

**Title:** Show HN: mcpeval – Lint and test MCP tool schemas before shipping

**Body:**

Building MCP servers is easy. Building ones that LLMs use correctly is hard.

Common failure modes: ambiguous descriptions (LLM picks wrong tool), generic param names like "data" (LLM passes garbage), missing enums (LLM invents invalid values), similar tools (LLM can't distinguish).

mcpeval catches these in CI — no API key needed for static analysis. It checks 13 anti-patterns, shows token budget per tool, and gives actionable fix suggestions.

Optional simulation mode sends queries to an LLM with your schemas and measures tool selection accuracy.

pip install mcpeval
mcpeval check my_server.json --ci

https://github.com/jashshah999/mcpeval

---

## Twitter/X Thread

Tweet 1:
I kept debugging why Claude picks the wrong MCP tool. Every time, the problem was in my schema — not my prompt.

So I built mcpeval: a linter that catches the 13 anti-patterns that confuse LLMs.

pip install mcpeval
mcpeval check your_server.json

[screenshot of bad_server output]

Tweet 2:
What it catches:
- Missing descriptions (LLM can't know when to use it)
- Generic params like "data", "value" (LLM passes garbage)  
- Missing enums on status/type fields
- Similar tools (>70% description overlap)
- Token hogs (one tool eating 50% of context)

Tweet 3:
Also has an LLM simulation mode — actually tests whether Claude/GPT picks the right tool for natural language queries.

"Find users named John" → expected: search_users → got: ✓
"Remove the old account" → expected: delete_user → got: ✗ (deactivate_user)

Tweet 4:
Runs in CI. Exit code 1 on failures.

mcpeval check schema.json --ci --json-output

No more "it works on my machine" → users report wrong tool selection in prod.

GitHub: https://github.com/jashshah999/mcpeval

---

## GitHub Issues/Discussions Posted

1. ✅ modelcontextprotocol/servers#3669 (schema quality) - https://github.com/modelcontextprotocol/servers/issues/3669#issuecomment-4376773226
2. ✅ modelcontextprotocol/servers#3537 (security audit) - https://github.com/modelcontextprotocol/servers/issues/3537#issuecomment-4376773271
3. ✅ modelcontextprotocol/modelcontextprotocol#1990 (conformance testsuite) - https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1990#issuecomment-4376773321
4. ✅ modelcontextprotocol/servers#4095 (filesystem descriptions) - https://github.com/modelcontextprotocol/servers/issues/4095#issuecomment-4376773850
5. ✅ modelcontextprotocol/modelcontextprotocol#1627 (conformance SEP) - https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1627#issuecomment-4376773905

## TODO
- [ ] Post to r/ChatGPTCoding
- [ ] Post to r/ClaudeAI  
- [ ] Post to HN (Show HN)
- [ ] Tweet thread
- [ ] Submit PR to awesome-mcp-servers list
- [ ] Comment on FastMCP testing-related issues
