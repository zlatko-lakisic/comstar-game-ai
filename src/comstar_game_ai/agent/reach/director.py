"""direct_agent calls with neutral directive fallback."""

from __future__ import annotations

import logging
from typing import Any, Callable

from ao_reach.run_status import ReachRunError, ReachRunStatus

from comstar_game_ai.agent.directive import Directive, neutral_directive, parse_directive
from comstar_game_ai.agent.reach.session import ReachSession

_LOGGER = logging.getLogger(__name__)

BATTLE_DIRECTOR = "client.battle_director"
CAMPAIGN_DIRECTOR = "client.campaign_director"
OPPONENT_MODELER = "client.opponent_modeler"
NARRATOR = "client.narrator"
CONSOLIDATOR = "client.consolidator"
DOCTRINE_INGESTOR = "client.doctrine_ingestor"
POST_MORTEM = "client.post_mortem"

GAME_QUERY_MCP = "client.game_query"

DEFAULT_TIMEOUTS: dict[str, float] = {
    BATTLE_DIRECTOR: 20.0,
    CAMPAIGN_DIRECTOR: 90.0,
    OPPONENT_MODELER: 120.0,
    NARRATOR: 15.0,
}


def _extract_text(result: dict[str, Any]) -> str:
    return str(result.get("text") or "").strip()


async def call_directive_agent(
    session: ReachSession,
    *,
    agent_provider_id: str,
    text: str,
    context: str = "",
    question_id: str,
    priority: str | int | None = "high",
    timeout: float | None = None,
    images: list[dict[str, Any]] | None = None,
    mcp_provider_ids: list[str] | None = None,
    on_status: Callable[[ReachRunStatus], None] | None = None,
    stale_question_ids: list[str] | None = None,
) -> Directive:
    """Call a directive-producing agent; every failure path returns neutral."""
    for stale_id in stale_question_ids or []:
        if stale_id and stale_id != question_id:
            try:
                await session.bridge.cancel(stale_id)
            except Exception:  # noqa: BLE001
                _LOGGER.debug("cancel stale %s failed", stale_id, exc_info=True)

    effective_timeout = timeout if timeout is not None else DEFAULT_TIMEOUTS.get(agent_provider_id, 60.0)
    mcps = mcp_provider_ids if mcp_provider_ids is not None else [GAME_QUERY_MCP]

    try:
        result = await session.bridge.direct_agent(
            agent_provider_id=agent_provider_id,
            text=text,
            context=context,
            question_id=question_id,
            priority=priority,
            timeout=effective_timeout,
            images=images,
            mcp_provider_ids=mcps,
            on_status=on_status,
        )
        return parse_directive(_extract_text(result))
    except TimeoutError:
        _LOGGER.warning("direct_agent timeout: %s (%s)", agent_provider_id, question_id)
        return neutral_directive(f"timeout:{agent_provider_id}")
    except ReachRunError as exc:
        _LOGGER.warning(
            "direct_agent error: %s (%s) code=%s",
            agent_provider_id,
            question_id,
            exc.code,
        )
        return neutral_directive(f"reach_error:{exc.code or 'unknown'}")
    except Exception as exc:  # noqa: BLE001
        _LOGGER.exception("direct_agent failed: %s (%s)", agent_provider_id, question_id)
        return neutral_directive(f"error:{type(exc).__name__}")


async def call_battle_director(
    session: ReachSession,
    *,
    text: str,
    context: str = "",
    question_id: str,
    images: list[dict[str, Any]] | None = None,
    stale_question_ids: list[str] | None = None,
    on_status: Callable[[ReachRunStatus], None] | None = None,
) -> Directive:
    return await call_directive_agent(
        session,
        agent_provider_id=BATTLE_DIRECTOR,
        text=text,
        context=context,
        question_id=question_id,
        priority="high",
        images=images,
        stale_question_ids=stale_question_ids,
        on_status=on_status,
    )


async def call_campaign_director(
    session: ReachSession,
    *,
    text: str,
    context: str = "",
    question_id: str,
    images: list[dict[str, Any]] | None = None,
    on_status: Callable[[ReachRunStatus], None] | None = None,
) -> Directive:
    return await call_directive_agent(
        session,
        agent_provider_id=CAMPAIGN_DIRECTOR,
        text=text,
        context=context,
        question_id=question_id,
        priority="high",
        images=images,
        on_status=on_status,
    )


async def call_narrator(
    session: ReachSession,
    *,
    text: str,
    question_id: str,
    on_status: Callable[[ReachRunStatus], None] | None = None,
) -> str:
    """Narrator is cosmetic; empty string on failure."""
    try:
        result = await session.bridge.direct_agent(
            agent_provider_id=NARRATOR,
            text=text,
            question_id=question_id,
            priority="realtime",
            timeout=DEFAULT_TIMEOUTS[NARRATOR],
            on_status=on_status,
        )
        return _extract_text(result)
    except Exception:  # noqa: BLE001
        _LOGGER.debug("narrator call failed", exc_info=True)
        return ""
