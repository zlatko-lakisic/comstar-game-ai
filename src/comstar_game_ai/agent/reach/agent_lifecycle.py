"""AO Reach agent lifecycle (`type: agent_state`) helpers.

Reach ≥0.18 / AO ≥2.10 push sticky per-agent frames: down / starting / pulling /
loading / ready / busy / stopping. ``loading`` is optional VRAM prewarm when the
agent YAML sets ``prewarm: true``. Wait on ``READY`` instead of guessing
cold-start wall-clock timeouts; keep ``timeout`` only as a hard abort safety net.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Callable

from ao_reach.agent_state import AgentLifecycleState, AgentStateUpdate
from ao_reach.session_bridge import SessionBridge

from comstar_game_ai.shared.config import repo_root

__all__ = [
    "AgentLifecycleState",
    "AgentStateUpdate",
    "DEFAULT_READY_SAFETY_S",
    "STATUS_PATH",
    "agent_state_payload",
    "attach_agent_state_listener",
    "format_agent_state",
    "read_agent_status",
    "wait_until_not_busy",
    "wait_until_ready",
    "write_agent_status",
]

_LOGGER = logging.getLogger(__name__)

#: Abort-only ceiling for ``wait_for_agent_state``. Pull + VRAM prewarm on a
#: shared GPU can take minutes; this is not the readiness signal.
DEFAULT_READY_SAFETY_S = 900.0

STATUS_PATH = repo_root() / "data" / "runtime" / "ao_agent_status.json"


def format_agent_state(update: AgentStateUpdate) -> str:
    """One operator-facing line for logs / overlay."""
    bare = update.agent_provider_id.removeprefix("client.") or update.agent_provider_id
    bits = [bare, update.state.value]
    if update.model:
        bits.append(update.model)
    if update.progress is not None:
        bits.append(f"{int(round(float(update.progress) * 100))}%")
    if update.detail:
        bits.append(str(update.detail)[:80])
    elif update.reason:
        bits.append(str(update.reason)[:60])
    return " ".join(bits)


def agent_state_payload(update: AgentStateUpdate) -> dict[str, Any]:
    """IPC / status-file payload (overlay AO_STATUS friendly)."""
    return {
        "summary": format_agent_state(update),
        "agent": update.agent_provider_id,
        "state": update.state.value,
        "phase": update.state.value,
        "status": update.state.value,
        "model": update.model,
        "progress": update.progress,
        "detail": update.detail,
        "reason": update.reason,
        "question_id": update.question_id,
    }


def write_agent_status(update: AgentStateUpdate, *, path: Path | None = None) -> None:
    """Persist latest agent_state for Process A (phase2) to poll without AO."""
    target = path or STATUS_PATH
    payload = agent_state_payload(update)
    payload["ts"] = time.time()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError:
        _LOGGER.debug("could not write agent status file", exc_info=True)


def read_agent_status(*, path: Path | None = None) -> dict[str, Any] | None:
    target = path or STATUS_PATH
    try:
        if not target.is_file():
            return None
        data = json.loads(target.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def attach_agent_state_listener(
    bridge: SessionBridge,
    *,
    on_update: Callable[[AgentStateUpdate], None] | None = None,
    write_status_file: bool = True,
) -> None:
    """Log + optional callback/file for every ``agent_state`` frame."""

    def _cb(update: AgentStateUpdate) -> None:
        _LOGGER.info("AO agent_state: %s", format_agent_state(update))
        if write_status_file:
            write_agent_status(update)
        if on_update is not None:
            try:
                on_update(update)
            except Exception:  # noqa: BLE001
                _LOGGER.debug("agent_state on_update failed", exc_info=True)

    bridge.on_agent_state(_cb)


async def wait_until_ready(
    bridge: SessionBridge,
    agent_provider_id: str,
    *,
    safety_timeout_s: float = DEFAULT_READY_SAFETY_S,
) -> AgentStateUpdate:
    """Block until the agent is idle and callable (``READY``).

    ``BUSY`` means a run is in flight — callers that need the GPU free should
    cancel that run first, then wait here.
    """
    current = bridge.agent_state(agent_provider_id)
    if current is AgentLifecycleState.READY:
        meta = bridge.agent_state_meta.get(agent_provider_id)
        if meta is not None:
            return meta
        return AgentStateUpdate(
            agent_provider_id=agent_provider_id, state=AgentLifecycleState.READY
        )
    if current is not None:
        _LOGGER.info(
            "waiting for %s ready (now %s, safety=%.0fs)",
            agent_provider_id,
            current.value,
            safety_timeout_s,
        )
    else:
        _LOGGER.info(
            "waiting for %s ready (no state yet, safety=%.0fs)",
            agent_provider_id,
            safety_timeout_s,
        )
    return await bridge.wait_for_agent_state(
        agent_provider_id,
        states={AgentLifecycleState.READY},
        timeout=safety_timeout_s,
    )


async def wait_until_not_busy(
    bridge: SessionBridge,
    agent_provider_id: str,
    *,
    safety_timeout_s: float = DEFAULT_READY_SAFETY_S,
) -> AgentStateUpdate | None:
    """Wait until the agent leaves ``BUSY`` (ready/down/starting/pulling/loading)."""
    current = bridge.agent_state(agent_provider_id)
    if current is not AgentLifecycleState.BUSY:
        return bridge.agent_state_meta.get(agent_provider_id)
    _LOGGER.info(
        "waiting for %s to leave busy (safety=%.0fs)",
        agent_provider_id,
        safety_timeout_s,
    )
    return await bridge.wait_for_agent_state(
        agent_provider_id,
        states={
            AgentLifecycleState.READY,
            AgentLifecycleState.DOWN,
            AgentLifecycleState.STARTING,
            AgentLifecycleState.PULLING,
            AgentLifecycleState.LOADING,
            AgentLifecycleState.STOPPING,
        },
        timeout=safety_timeout_s,
    )
