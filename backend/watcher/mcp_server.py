"""MCP server exposing the reasoning engine to coding agents.

Wire into Claude Code with:

  claude mcp add watcher -- python -m watcher.mcp_server

(run from backend/, or set WATCHER_GRAPH to an absolute path first)

Then an agent editing payments code can ask get_context_for
("services/payments/handler.py") and get root-cause-level context -
"this service inherits s3:* from a shared terraform module, here's the
one fix" - instead of forty lint-grade alerts.

Uses the official `mcp` python sdk (FastMCP). The tool functions live in
watcher.tools; this file only adapts them, so the HTTP API and the agent
surface can never drift apart.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from . import tools

mcp = FastMCP("watcher")

# FastMCP builds schemas from signatures + docstrings, which watcher.tools
# already keeps agent-grade. Register them directly.
for fn in tools.TOOLS:
    mcp.tool()(fn)


if __name__ == "__main__":
    mcp.run()
