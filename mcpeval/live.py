"""Connect to a running MCP server and extract its tool schemas for analysis."""

from __future__ import annotations

import json
import subprocess

from .schema import MCPServerSpec, Tool, _extract_params


def connect_stdio(command: list[str], timeout: int = 10) -> MCPServerSpec:
    """Connect to an MCP server via stdio and list its tools.

    Args:
        command: Command to start the MCP server (e.g., ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/tmp"])
        timeout: Seconds to wait for response
    """
    # MCP protocol: send initialize, then tools/list
    init_msg = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "mcpeval", "version": "0.1.0"},
        },
    }

    list_tools_msg = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {},
    }

    initialized_msg = {
        "jsonrpc": "2.0",
        "method": "notifications/initialized",
    }

    try:
        proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Send initialize
        _send(proc, init_msg)
        _read_response(proc, timeout)

        # Send initialized notification
        _send(proc, initialized_msg)

        # Send tools/list
        _send(proc, list_tools_msg)
        response = _read_response(proc, timeout)

        proc.terminate()

        if "result" not in response:
            raise RuntimeError(f"No result in tools/list response: {response}")

        tools_data = response["result"].get("tools", [])
        tools = []
        for td in tools_data:
            params = _extract_params(td)
            tools.append(Tool(
                name=td.get("name", "unknown"),
                description=td.get("description", ""),
                parameters=params,
                raw_schema=td,
            ))

        return MCPServerSpec(
            name=f"live:{' '.join(command[:2])}",
            tools=tools,
            source=f"stdio:{' '.join(command)}",
        )

    except subprocess.TimeoutExpired:
        proc.kill()
        raise RuntimeError(f"MCP server timed out after {timeout}s")
    except FileNotFoundError:
        raise RuntimeError(f"Command not found: {command[0]}")


def _send(proc: subprocess.Popen, msg: dict) -> None:
    data = json.dumps(msg)
    content = f"Content-Length: {len(data)}\r\n\r\n{data}"
    proc.stdin.write(content.encode())
    proc.stdin.flush()


def _read_response(proc: subprocess.Popen, timeout: int) -> dict:
    """Read a JSON-RPC response from the process stdout."""
    import select
    import time

    deadline = time.time() + timeout
    buffer = b""

    while time.time() < deadline:
        remaining = deadline - time.time()
        ready, _, _ = select.select([proc.stdout], [], [], min(remaining, 0.1))
        if ready:
            chunk = proc.stdout.read1(4096) if hasattr(proc.stdout, 'read1') else proc.stdout.read(4096)
            if not chunk:
                break
            buffer += chunk

            # Try to parse JSON-RPC from buffer
            text = buffer.decode("utf-8", errors="replace")
            if "\r\n\r\n" in text:
                _, body = text.split("\r\n\r\n", 1)
                try:
                    return json.loads(body)
                except json.JSONDecodeError:
                    continue

    raise RuntimeError("Timeout waiting for MCP server response")
