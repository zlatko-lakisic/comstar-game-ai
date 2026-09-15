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

import inspect
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
MAP_TARGET_VISION = "client.map_target_vision"
DETECT_YOLOX_NANO = "detect_yolox_nano"
DETECT_RTW_CAMPAIGN = "client.detect_rtw_campaign"
CONSOLIDATOR = "client.consolidator"
DOCTRINE_INGESTOR = "client.doctrine_ingestor"
POST_MORTEM = "client.post_mortem"

GAME_QUERY_MCP = "client.game_query"

#: Abort-only safety nets for ``direct_agent`` / ``chat``. Readiness is
#: ``wait_until_ready`` on AO ``agent_state`` (pulling/starting → ready), not
#: these numbers. Keep them high so a slow GPU swap does not abandon a lease
#: mid-flight; Reach cancels the engine run when the client timeout fires.
DEFAULT_TIMEOUTS: dict[str, float] = {
    BATTLE_DIRECTOR: 600.0,
    CAMPAIGN_DIRECTOR: 600.0,
    MODAL_VISION: 600.0,
    MAP_TARGET_VISION: 600.0,
    DETECT_YOLOX_NANO: 120.0,
    DETECT_RTW_CAMPAIGN: 120.0,
    OPPONENT_MODELER: 600.0,
    NARRATOR: 300.0,
    CONSOLIDATOR: 600.0,
    DOCTRINE_INGESTOR: 600.0,
    POST_MORTEM: 600.0,
}

#: How long to wait for ``agent_state=ready`` before even sending the call.
READY_SAFETY_S = 900.0

#: Logged once when an installed ao_reach drops JSON-mode kwargs.
_logged_direct_agent_strip: set[str] = set()


def _extract_text(result: dict[str, Any]) -> str:
    return str(result.get("text") or "").strip()


def _direct_agent_kwargs(bridge: Any, **kwargs: Any) -> dict[str, Any]:
    """Pass only kwargs the installed ``SessionBridge.direct_agent`` accepts.

    Older ao_reach builds reject ``response_format`` / ``json_schema`` with
    TypeError before the agent runs; that used to collapse every turn to hold.
    Newer builds that accept those kwargs still get them.
    """
    fn = getattr(bridge, "direct_agent", None)
    if fn is None:
        return kwargs
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return kwargs
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return kwargs
    dropped = [k for k in kwargs if k not in params]
    if dropped:
        key = ",".join(sorted(dropped))
        if key not in _logged_direct_agent_strip:
            _logged_direct_agent_strip.add(key)
            _LOGGER.warning(
                "ao_reach direct_agent does not accept %s — calling without "
                "(upgrade ao_reach for JSON-mode constraints)",
                dropped,
            )
        return {k: v for k, v in kwargs.items() if k in params}
    return kwargs


async def _bridge_direct_agent(bridge: Any, **kwargs: Any) -> dict[str, Any]:
    return await bridge.direct_agent(**_direct_agent_kwargs(bridge, **kwargs))


async def _wait_ready(session: ReachSession, agent_provider_id: str) -> None:
    from comstar_game_ai.agent.reach.agent_lifecycle import wait_until_ready

    try:
        update = await wait_until_ready(
            session.bridge, agent_provider_id, safety_timeout_s=READY_SAFETY_S
        )
        _LOGGER.info(
            "AO ready: %s state=%s model=%s",
            agent_provider_id,
            update.state.value,
            update.model,
        )
    except TimeoutError:
        _LOGGER.warning(
            "AO agent %s never reached ready within %.0fs — calling anyway",
            agent_provider_id,
            READY_SAFETY_S,
        )
    except Exception:  # noqa: BLE001
        _LOGGER.debug("wait_until_ready failed for %s", agent_provider_id, exc_info=True)


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

    await _wait_ready(session, agent_provider_id)

    try:
        result = await _bridge_direct_agent(
            session.bridge,
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
        raw_text = _extract_text(result)
        directive = parse_directive(raw_text)
        if (
            directive.intent.objective == "hold"
            and directive.commentary.startswith(("malformed", "empty", "not_object"))
            and raw_text
        ):
            _LOGGER.warning(
                "directive parse failed (%s) raw_preview=%r",
                directive.commentary,
                raw_text[:240],
            )
        return directive
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
        # AO 2.10+: chat timeouts surface as code=timeout with a detail string
        # (e.g. "Ollama /api/chat timed out after 600s"). Prefer that over opaque
        # run_failed so deliberate logs and hold commentary stay actionable.
        code = (exc.code or "unknown").strip() or "unknown"
        detail = (exc.detail or exc.message or "").strip()
        _LOGGER.warning(
            "direct_agent error: %s (%s) code=%s detail=%s",
            agent_provider_id,
            question_id,
            code,
            (detail[:200] if detail else "-"),
        )
        if code == "timeout" or "timed out" in detail.lower():
            await _abandon(session, question_id)
            return neutral_directive(f"timeout:{agent_provider_id}")
        return neutral_directive(f"reach_error:{code}")
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
    """Campaign director call.

    `client.game_query` is registered on the agent provider (C10 / YAML mcp list)
    for any future non-JSON path. JSON mode still cannot run tools, so
    `mcp_provider_ids` stays empty here: the composed brief in `context` is the
    primary path, and tool-usage logging reports zero calls under this mode —
    which is an acceptable measured result per the contract rework.
    """
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
        mcp_provider_ids=[],
        on_status=on_status,
    )


def modal_vision_schema() -> dict[str, Any]:
    """What a panel looks like, shaped for constrained decoding.

    `modal_kind` leads because it is the answer that matters most and the cheapest
    to reach: on a clear map the object can be complete in a dozen tokens.

    `candidates` has to be an array — a panel can show a check and an X — so it is
    the one unbounded field here, and unbounded fields are where a grammar-guided
    model runs away, having only ever been offered valid next tokens. `maxItems`
    is the brake. Three is above anything this UI shows; a scroll footer offers
    two.

    Only `modal_kind` and `reason` are required. Under constrained decoding a
    required field is generated rather than considered, so requiring `candidates`
    would collect invented buttons on a clear map — which is the one failure that
    costs a run, because the handler would click one.
    """
    return {
        "type": "object",
        "properties": {
            "modal_kind": {
                "type": "string",
                "enum": [
                    "none",
                    "diplomacy_negotiation",
                    "left_alert_panel",
                    "senate_mission",
                    "advisor_event",
                    "pause_menu",
                    "pre_battle",
                    "other",
                ],
            },
            "reason": {"type": "string"},
            # Kept despite the token cost: `_inside_bounds` uses it to throw out a
            # button located outside the panel it supposedly belongs to. Fixed at
            # four, so it cannot run away the way an open array can.
            "dialog_bounds_norm": {
                "type": "array",
                "minItems": 4,
                "maxItems": 4,
                "items": {"type": "number"},
            },
            "candidates": {
                "type": "array",
                "maxItems": 3,
                "items": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["accept", "reject", "close", "continue"],
                        },
                        "x_norm": {"type": "number"},
                        "y_norm": {"type": "number"},
                        "confidence": {"type": "number"},
                    },
                    "required": ["action", "x_norm", "y_norm", "confidence"],
                },
            },
        },
        "required": ["modal_kind", "reason"],
    }


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
    await _wait_ready(session, agent_provider_id)
    try:
        result = await _bridge_direct_agent(
            session.bridge,
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
    await _wait_ready(session, agent_provider_id)
    try:
        result = await _bridge_direct_agent(
            session.bridge,
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
    await _wait_ready(session, NARRATOR)
    try:
        result = await _bridge_direct_agent(
            session.bridge,
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
    """Modal vision call; empty string on failure.

    Runs in JSON mode for the same reason the directors do: without it the engine
    sanitizes the answer into something speakable, which on a JSON object means
    keeping the last prose field and discarding the structure. A live run logged
    twelve calls and zero usable results, the replies being `none` and `nothing
    over the map` — the latter being verbatim the `reason` string out of the
    prompt's own clear-map example. The model had answered correctly every time.
    """
    from comstar_game_ai.shared.config import load_config

    cfg = load_config()
    vision_model = str((cfg.get("ao") or {}).get("vision_model") or "llava:7b").strip()
    effective_text = text
    if vision_model and not text.lstrip().lower().startswith("[model="):
        effective_text = f"[model={vision_model}]\n{text}"
    await _wait_ready(session, MODAL_VISION)
    try:
        result = await _bridge_direct_agent(
            session.bridge,
            agent_provider_id=MODAL_VISION,
            text=effective_text,
            context=context,
            question_id=question_id,
            priority="high",
            timeout=timeout if timeout is not None else DEFAULT_TIMEOUTS[MODAL_VISION],
            images=images,
            response_format=JSON_OBJECT_RESPONSE_FORMAT,
            json_schema=modal_vision_schema(),
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


def map_target_vision_schema() -> dict[str, Any]:
    """Full-window settlement locate — see map_target_vision module."""
    from comstar_game_ai.game_io.campaign.map_target_vision import map_target_vision_schema as _schema

    return _schema()


async def call_map_target_vision(
    session: ReachSession,
    *,
    text: str,
    question_id: str,
    images: list[dict[str, Any]],
    context: str = "",
    timeout: float | None = None,
    on_status: Callable[[ReachRunStatus], None] | None = None,
    raise_errors: bool = False,
    json_schema: dict[str, Any] | None = None,
) -> str:
    """Map-target vision call; empty string on failure."""
    from comstar_game_ai.shared.config import load_config

    cfg = load_config()
    vision_model = str((cfg.get("ao") or {}).get("vision_model") or "llava:7b").strip()
    effective_text = text
    if vision_model and not text.lstrip().lower().startswith("[model="):
        effective_text = f"[model={vision_model}]\n{text}"
    schema = json_schema if json_schema is not None else map_target_vision_schema()
    await _wait_ready(session, MAP_TARGET_VISION)
    try:
        result = await _bridge_direct_agent(
            session.bridge,
            agent_provider_id=MAP_TARGET_VISION,
            text=effective_text,
            context=context,
            question_id=question_id,
            priority="high",
            timeout=timeout if timeout is not None else DEFAULT_TIMEOUTS[MAP_TARGET_VISION],
            images=images,
            response_format=JSON_OBJECT_RESPONSE_FORMAT,
            json_schema=schema,
            on_status=on_status,
        )
        return _extract_text(result)
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning("map_target_vision call failed: %s: %s", type(exc).__name__, exc)
        if isinstance(exc, TimeoutError):
            await _abandon(session, question_id)
        if raise_errors:
            raise
        return ""


async def call_map_object_detection(
    session: ReachSession,
    *,
    images: list[dict[str, Any]],
    question_id: str,
    agent_provider_id: str | None = None,
    text: str = "detect",
    context: str = "",
    timeout: float | None = None,
    on_status: Callable[[ReachRunStatus], None] | None = None,
    raise_errors: bool = False,
) -> str:
    """Run AO object_detection; return raw JSON text (empty string on failure).

    Does not request JSON-mode schema constraints — the detection provider
    already returns structured JSON and prose sanitizers must not rewrite it.
    """
    from comstar_game_ai.shared.config import load_config

    cfg = load_config()
    ao = cfg.get("ao") or {}
    agent_id = (
        agent_provider_id
        or str(ao.get("detection_agent") or DETECT_YOLOX_NANO).strip()
        or DETECT_YOLOX_NANO
    )
    # Catalog detectors are not in the session overlay and never get agent_state
    # READY frames — wait_until_ready would hang until the safety timeout.
    registered = {
        str(x) for x in (getattr(session.bridge, "registered_agent_ids", None) or [])
    }
    has_state = session.bridge.agent_state(agent_id) is not None
    if agent_id in registered or has_state:
        await _wait_ready(session, agent_id)
    try:
        result = await _bridge_direct_agent(
            session.bridge,
            agent_provider_id=agent_id,
            text=text,
            context=context,
            question_id=question_id,
            priority="high",
            timeout=timeout
            if timeout is not None
            else DEFAULT_TIMEOUTS.get(agent_id, 120.0),
            images=images,
            on_status=on_status,
        )
        return _extract_text(result)
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning(
            "map_object_detection call failed (%s): %s: %s",
            agent_id,
            type(exc).__name__,
            exc,
        )
        if isinstance(exc, TimeoutError):
            await _abandon(session, question_id)
        if raise_errors:
            raise
        return ""
