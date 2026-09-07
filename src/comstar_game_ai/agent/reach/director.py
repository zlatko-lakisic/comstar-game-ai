"""direct_agent calls with neutral directive fallback.

Two engine behaviours decide the shape of this module, and neither is guessable from
the call signature.

**The prose path rewrites JSON.** A plain `direct_agent` answer goes through
`sanitize_user_facing_prose`, which exists to make an answer speakable and therefore
unwraps a JSON object down to the one field a voice assistant should read aloud. A
nine-field directive came back as the single word `normal`, with `ok: true`. Anything
that must parse asks for JSON mode, where the schema also constrains decoding — so an
objective outside the enum is not merely rejected, it cannot be written.

**JSON mode brings no crew, and no persona.** It calls the model directly, so it
carries no tools, and the agent's role, goal and backstory — including every skill the
overlay packer inlined into that backstory — are not sent. Only the model tag is read
from the catalog entry. Everything a JSON-mode agent needs to know has to travel in
`text` and `context`, which is why the questions in `prompts` carry their own framing
rather than relying on the provider YAML.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from ao_reach.run_status import ReachRunError, ReachRunStatus

from comstar_game_ai.agent.directive import (
    JSON_OBJECT_RESPONSE_FORMAT,
    Directive,
    battle_directive_schema,
    campaign_directive_schema,
    neutral_directive,
    parse_directive,
)
from comstar_game_ai.agent.reach.prompts import (
    consolidation_question,
    doctrine_triage_question,
    opponent_read_question,
    post_mortem_question,
)
from comstar_game_ai.agent.reach.session import ReachSession

_LOGGER = logging.getLogger(__name__)

BATTLE_DIRECTOR = "client.battle_director"
CAMPAIGN_DIRECTOR = "client.campaign_director"
OPPONENT_MODELER = "client.opponent_modeler"
NARRATOR = "client.narrator"
MODAL_VISION = "client.modal_vision"
CONSOLIDATOR = "client.consolidator"
DOCTRINE_INGESTOR = "client.doctrine_ingestor"
POST_MORTEM = "client.post_mortem"

GAME_QUERY_MCP = "client.game_query"

#: Measured against ada, not chosen for comfort. A cold llama3.1:8b spends most of a
#: minute loading before it emits a token, and the campaign director's prompt carries
#: a belief brief and a schema on top of that.
#:
#: Timing out short is not the cheap option it looks like. The GPU broker admits a
#: request on a worker thread, so a client that walks away while its turn is pending
#: leaves the lease granted and unheld — and the next model to ask queues behind a
#: slot nobody will release. One impatient 90-second vision call wedged every text
#: agent on the host until the pod was restarted.
DEFAULT_TIMEOUTS: dict[str, float] = {
    BATTLE_DIRECTOR: 60.0,
    CAMPAIGN_DIRECTOR: 300.0,
    MODAL_VISION: 120.0,
    OPPONENT_MODELER: 300.0,
    NARRATOR: 60.0,
    CONSOLIDATOR: 300.0,
    DOCTRINE_INGESTOR: 300.0,
    POST_MORTEM: 300.0,
}


def _extract_text(result: dict[str, Any]) -> str:
    return str(result.get("text") or "").strip()


async def _abandon(session: ReachSession, question_id: str) -> None:
    """Tell the engine to stop work we have stopped waiting for.

    Giving up locally is not the same as giving up: the engine keeps running an
    abandoned request to completion, and it executes one at a time across the whole
    install. So a timeout that stays quiet does not cost one directive, it holds the
    only execution slot until the dead work finishes — the next turn's call queues
    behind an answer nobody will read, times out in its turn, and the run degrades
    into neutral directives that look like a model being careful.
    """
    try:
        await session.bridge.cancel(question_id)
    except Exception:  # noqa: BLE001
        _LOGGER.debug("cancel after timeout failed for %s", question_id, exc_info=True)


def _default_mcp_ids(session: ReachSession) -> list[str]:
    """Belief tools, but only the ones this session managed to register.

    Requesting game_query unconditionally cost a whole 20-turn run: its stdio server
    had failed to start, the engine rejected every director call with `unknown
    catalog id 'client.game_query'`, and each rejection became a neutral directive.
    Twenty-one turns of "hold" that looked like caution. A missing optional tool
    should cost the tools, not the reasoning.
    """
    available = getattr(session, "available_mcp_ids", None)
    if available is None:
        return [GAME_QUERY_MCP]
    if GAME_QUERY_MCP in available:
        return [GAME_QUERY_MCP]
    _LOGGER.warning(
        "%s is not registered in this session — calling without belief tools", GAME_QUERY_MCP
    )
    return []


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
    response_format: dict[str, Any] | None = None,
    json_schema: dict[str, Any] | None = None,
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
    mcps = mcp_provider_ids if mcp_provider_ids is not None else _default_mcp_ids(session)

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
            response_format=response_format,
            json_schema=json_schema,
            on_status=on_status,
        )
        return parse_directive(_extract_text(result))
    except TimeoutError:
        _LOGGER.warning(
            "direct_agent timeout after %.0fs: %s (%s)",
            effective_timeout,
            agent_provider_id,
            question_id,
        )
        await _abandon(session, question_id)
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
        response_format=JSON_OBJECT_RESPONSE_FORMAT,
        json_schema=battle_directive_schema(),
        mcp_provider_ids=[],
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
        response_format=JSON_OBJECT_RESPONSE_FORMAT,
        json_schema=campaign_directive_schema(),
        # JSON mode runs no crew, so it can hold no tools. Asking for belief tools
        # here would be asking for something the pipeline cannot deliver; the belief
        # the director needs is composed into `context` instead, where we can also
        # be sure it arrived.
        mcp_provider_ids=[],
        on_status=on_status,
    )


OPPONENT_READ_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "faction": {"type": "string"},
        "posture": {
            "type": "string",
            "enum": ["passive", "defensive", "opportunistic", "aggressive", "unknown"],
        },
        "likely_intent": {"type": "string"},
        "evidence": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number"},
    },
    "required": ["faction", "posture", "likely_intent", "confidence"],
}

DOCTRINE_PROPOSALS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "proposals": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "heading": {"type": "string"},
                    "body": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["heading", "body", "confidence"],
            },
        }
    },
    "required": ["proposals"],
}

DOCTRINE_TRIAGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "destination": {"type": "string", "enum": ["rule", "doctrine", "corpus"]},
                    "why": {"type": "string"},
                },
                "required": ["title", "destination"],
            },
        }
    },
    "required": ["sections"],
}


async def call_structured_agent(
    session: ReachSession,
    *,
    agent_provider_id: str,
    text: str,
    json_schema: dict[str, Any],
    context: str = "",
    question_id: str,
    priority: str | int | None = "normal",
    timeout: float | None = None,
    on_status: Callable[[ReachRunStatus], None] | None = None,
) -> dict[str, Any]:
    """A JSON-mode call for an agent whose answer is data, not a directive.

    Returns the parsed object, or `{}` on any failure. Unlike a directive there is no
    meaningful neutral value for an opponent read or a doctrine proposal, and an empty
    dict is the honest way to say the analysis did not happen.
    """
    try:
        result = await session.bridge.direct_agent(
            agent_provider_id=agent_provider_id,
            text=text,
            context=context,
            question_id=question_id,
            priority=priority,
            timeout=timeout if timeout is not None else DEFAULT_TIMEOUTS.get(agent_provider_id, 120.0),
            mcp_provider_ids=[],
            response_format=JSON_OBJECT_RESPONSE_FORMAT,
            json_schema=json_schema,
            on_status=on_status,
        )
        payload = json.loads(_extract_text(result) or "{}")
        return payload if isinstance(payload, dict) else {}
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning(
            "%s failed: %s: %s", agent_provider_id, type(exc).__name__, exc
        )
        if isinstance(exc, TimeoutError):
            await _abandon(session, question_id)
        return {}


async def call_prose_agent(
    session: ReachSession,
    *,
    agent_provider_id: str,
    text: str,
    context: str = "",
    question_id: str,
    priority: str | int | None = "normal",
    timeout: float | None = None,
    on_status: Callable[[ReachRunStatus], None] | None = None,
) -> str:
    """A prose call for an agent whose answer is meant to be read by a person.

    The prose path is right here: sanitizing an answer that a human will read is what
    the sanitizer is for, and there is no object for it to unwrap.
    """
    try:
        result = await session.bridge.direct_agent(
            agent_provider_id=agent_provider_id,
            text=text,
            context=context,
            question_id=question_id,
            priority=priority,
            timeout=timeout if timeout is not None else DEFAULT_TIMEOUTS.get(agent_provider_id, 180.0),
            mcp_provider_ids=[],
            on_status=on_status,
        )
        return _extract_text(result)
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning("%s failed: %s: %s", agent_provider_id, type(exc).__name__, exc)
        if isinstance(exc, TimeoutError):
            await _abandon(session, question_id)
        return ""


async def call_opponent_modeler(
    session: ReachSession,
    *,
    faction: str,
    context: str = "",
    question_id: str,
    on_status: Callable[[ReachRunStatus], None] | None = None,
) -> dict[str, Any]:
    return await call_structured_agent(
        session,
        agent_provider_id=OPPONENT_MODELER,
        text=opponent_read_question(faction),
        json_schema=OPPONENT_READ_SCHEMA,
        context=context,
        question_id=question_id,
        on_status=on_status,
    )


async def call_consolidator(
    session: ReachSession,
    *,
    record_count: int,
    context: str = "",
    question_id: str,
    on_status: Callable[[ReachRunStatus], None] | None = None,
) -> dict[str, Any]:
    return await call_structured_agent(
        session,
        agent_provider_id=CONSOLIDATOR,
        text=consolidation_question(record_count),
        json_schema=DOCTRINE_PROPOSALS_SCHEMA,
        context=context,
        question_id=question_id,
        on_status=on_status,
    )


async def call_doctrine_ingestor(
    session: ReachSession,
    *,
    document_name: str,
    context: str = "",
    question_id: str,
    on_status: Callable[[ReachRunStatus], None] | None = None,
) -> dict[str, Any]:
    return await call_structured_agent(
        session,
        agent_provider_id=DOCTRINE_INGESTOR,
        text=doctrine_triage_question(document_name),
        json_schema=DOCTRINE_TRIAGE_SCHEMA,
        context=context,
        question_id=question_id,
        on_status=on_status,
    )


async def call_post_mortem(
    session: ReachSession,
    *,
    outcome: str,
    context: str = "",
    question_id: str,
    on_status: Callable[[ReachRunStatus], None] | None = None,
) -> str:
    return await call_prose_agent(
        session,
        agent_provider_id=POST_MORTEM,
        text=post_mortem_question(outcome),
        context=context,
        question_id=question_id,
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
    except Exception as exc:  # noqa: BLE001
        _LOGGER.debug("narrator call failed", exc_info=True)
        if isinstance(exc, TimeoutError):
            # Cosmetic, but it still holds the one execution slot the whole install
            # shares, and a directive would be queued behind it.
            await _abandon(session, question_id)
        return ""


async def call_modal_vision(
    session: ReachSession,
    *,
    text: str,
    question_id: str,
    images: list[dict[str, Any]],
    context: str = "",
    timeout: float | None = None,
    on_status: Callable[[ReachRunStatus], None] | None = None,
    raise_errors: bool = False,
) -> str:
    """Modal vision call; empty string on failure."""
    from comstar_game_ai.shared.config import load_config

    cfg = load_config()
    vision_model = str((cfg.get("ao") or {}).get("vision_model") or "llava:7b").strip()
    effective_text = text
    if vision_model and not text.lstrip().lower().startswith("[model="):
        effective_text = f"[model={vision_model}]\n{text}"
    try:
        result = await session.bridge.direct_agent(
            agent_provider_id=MODAL_VISION,
            text=effective_text,
            context=context,
            question_id=question_id,
            priority="high",
            timeout=timeout if timeout is not None else DEFAULT_TIMEOUTS[MODAL_VISION],
            images=images,
            on_status=on_status,
        )
        return _extract_text(result)
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning("modal_vision call failed: %s: %s", type(exc).__name__, exc)
        if isinstance(exc, TimeoutError):
            await _abandon(session, question_id)
        if raise_errors:
            raise
        return ""
