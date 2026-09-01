"""Read-only game query MCP (tunnel) backed by the belief store."""

from __future__ import annotations

import json
import logging
import sys
from typing import TYPE_CHECKING, Any

from ao_reach.mcp_bootstrap import SessionMcpBootstrapResult
from ao_reach.mcp_session_spec import McpSessionSpec, McpSessionTransport, session_tunnel_mcp_entry

from comstar_game_ai.agent.belief.store import BeliefStore, belief_snapshot_path

if TYPE_CHECKING:
    from ao_reach.connection_config import ReachConnectionConfig
    from ao_reach.local_mcp_host import LocalMcpHost

_LOGGER = logging.getLogger(__name__)

GAME_QUERY_BARE_ID = "game_query"
GAME_QUERY_ALIAS = "game_query"
GAME_QUERY_CLIENT_ID = "client.game_query"
GAME_QUERY_MODULE = "comstar_game_ai.agent.reach.mcp_game_query"

_TOOLS = (
    {
        "name": "get_army",
        "description": "Observable belief about an army by id",
        "inputSchema": {
            "type": "object",
            "properties": {"army_id": {"type": "string"}},
            "required": ["army_id"],
        },
    },
    {
        "name": "get_settlement",
        "description": "Observable belief about a settlement by id",
        "inputSchema": {
            "type": "object",
            "properties": {"settlement_id": {"type": "string"}},
            "required": ["settlement_id"],
        },
    },
    {
        "name": "get_history",
        "description": "Recent observable history entries",
        "inputSchema": {
            "type": "object",
            "properties": {"n": {"type": "integer", "minimum": 1, "maximum": 100}},
        },
    },
    {
        "name": "get_faction_belief",
        "description": "Observable belief about a faction",
        "inputSchema": {
            "type": "object",
            "properties": {"faction": {"type": "string"}},
            "required": ["faction"],
        },
    },
    {
        "name": "explain_unit",
        "description": "Unit type reference from belief store",
        "inputSchema": {
            "type": "object",
            "properties": {"unit_type": {"type": "string"}},
            "required": ["unit_type"],
        },
    },
)


def _load_store() -> BeliefStore:
    return BeliefStore.load(belief_snapshot_path())


def _tool_result(payload: Any) -> dict[str, Any]:
    text = json.dumps(payload, indent=2) if payload is not None else "null"
    return {"content": [{"type": "text", "text": text}]}


def _dispatch_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    store = _load_store()
    if name == "get_army":
        return _tool_result(store.get_army(str(arguments.get("army_id") or "")))
    if name == "get_settlement":
        return _tool_result(store.get_settlement(str(arguments.get("settlement_id") or "")))
    if name == "get_history":
        n = arguments.get("n", 10)
        return _tool_result(store.get_history(int(n) if isinstance(n, (int, float)) else 10))
    if name == "get_faction_belief":
        return _tool_result(store.get_faction_belief(str(arguments.get("faction") or "")))
    if name == "explain_unit":
        return _tool_result(store.explain_unit(str(arguments.get("unit_type") or "")))
    return _tool_result({"error": f"unknown tool: {name}"})


class GameQueryMcpBootstrap:
    """Start game_query stdio MCP and register tunnel entry."""

    async def prepare(
        self,
        host: LocalMcpHost,
        *,
        mcp_tunnel: bool,
        config: ReachConnectionConfig | None = None,
    ) -> SessionMcpBootstrapResult:
        if not mcp_tunnel:
            return SessionMcpBootstrapResult(
                warnings=["mcp_tunnel disabled — client.game_query unavailable"]
            )

        spec = McpSessionSpec(
            bare_id=GAME_QUERY_BARE_ID,
            alias=GAME_QUERY_ALIAS,
            transport=McpSessionTransport.STDIO_TUNNEL,
            description="Read-only observable game state queries",
            python_module=GAME_QUERY_MODULE,
        )

        try:
            if not host.is_alias_running(spec.alias):
                await host.start_python_module(alias=spec.alias, module=spec.python_module or GAME_QUERY_MODULE)
        except RuntimeError as exc:
            _LOGGER.warning("game_query MCP unavailable: %s", exc)
            return SessionMcpBootstrapResult(
                warnings=[f"client.game_query unavailable: {exc}"],
            )

        return SessionMcpBootstrapResult(
            mcps=[
                session_tunnel_mcp_entry(
                    client_id=spec.client_id,
                    description=spec.description,
                    alias=spec.alias,
                )
            ],
            active_tunnel_bare_ids=[spec.bare_id],
        )


def main() -> None:
    """Minimal stdio MCP server for game_query tools."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        method = req.get("method")
        req_id = req.get("id")
        if method == "initialize":
            _reply(
                req_id,
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "game-query", "version": "0.1.0"},
                },
            )
        elif method == "tools/list":
            _reply(req_id, {"tools": list(_TOOLS)})
        elif method == "tools/call":
            params = req.get("params") or {}
            name = str(params.get("name") or "")
            args = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
            _reply(req_id, _dispatch_tool(name, args))


def _reply(req_id: object, result: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": req_id, "result": result}) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
