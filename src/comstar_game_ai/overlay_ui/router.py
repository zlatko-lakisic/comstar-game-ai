"""Translate the Process A/B event stream into overlay updates.

Pure: no Qt, no sockets. The overlay's semantics — which event means the agent is
deliberating, which keys stay lit, when the leash appears — are the part most
worth testing, and they are the part hardest to test through a live window.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from comstar_game_ai.overlay_ui.state import SurfaceState, coerce_state
from comstar_game_ai.shared.ipc.events import EventKind

#: Only these stay lit while held. Ctrl held is what makes "2" mean control
#: group two, so a stuck modifier has to be visible; a stuck letter does not.
MODIFIERS = frozenset({"ctrl", "control", "alt", "shift", "win"})

_CHAT_KINDS = {
    EventKind.AO_REQUEST,
    EventKind.AO_STATUS,
    EventKind.AO_RESULT,
    EventKind.INTENT_DECLARED,
    EventKind.VERIFICATION,
}


@dataclass(frozen=True)
class OverlayUpdate:
    """What one event should change on screen. Absent fields mean 'leave alone'."""

    state: SurfaceState | None = None
    flash_key: str | None = None
    held_keys: frozenset[str] | None = None
    pointer: tuple[int, int] | None = None
    pointer_synthetic: bool = True
    leash: tuple[tuple[int, int], tuple[int, int]] | None = None
    clear_leash: bool = False
    chat_line: str | None = None


def _point(value: Any) -> tuple[int, int] | None:
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        try:
            return (int(value[0]), int(value[1]))
        except (TypeError, ValueError):
            return None
    return None


def _summarise(kind: EventKind, payload: dict[str, Any]) -> str:
    """One readable line per event, favouring the fields an operator watches."""
    if kind is EventKind.AO_STATUS:
        bits = []
        phase = payload.get("phase") or payload.get("status")
        if phase:
            bits.append(str(phase))
        queue = payload.get("queue_position", payload.get("queuePosition"))
        if queue not in (None, ""):
            bits.append(f"queue #{queue}")
        latency = payload.get("latency_ms", payload.get("latencyMs"))
        if latency not in (None, ""):
            bits.append(f"{latency} ms")
        if bits:
            return f"status: {' · '.join(bits)}"
    if kind is EventKind.VERIFICATION:
        verdict = payload.get("ok")
        label = "ok" if verdict else "failed"
        if verdict is None:
            label = "?"
        return f"verify: {label} {payload.get('summary', payload.get('detail', ''))}".strip()

    summary = payload.get("summary") or payload.get("detail") or payload.get("text")
    if not summary:
        interesting = {k: v for k, v in payload.items() if k not in {"ts", "request_id"}}
        summary = str(interesting or payload)
    return f"{kind.value}: {summary}"


@dataclass
class EventRouter:
    """Holds the little state the overlay needs across events."""

    state: SurfaceState = SurfaceState.IDLE
    held: set[str] = field(default_factory=set)

    def route(self, kind: Any, payload: dict[str, Any] | None) -> OverlayUpdate:
        payload = payload or {}
        try:
            kind = EventKind(kind)
        except ValueError:
            return OverlayUpdate()

        update = OverlayUpdate()

        if kind is EventKind.CONTROL_STATE:
            update = replace(update, state=coerce_state(payload.get("state")))
        elif kind is EventKind.FREEZE:
            # The game is paused precisely so the agent can think.
            update = replace(update, state=SurfaceState.DELIBERATING)
        elif kind is EventKind.RESUME:
            update = replace(update, state=SurfaceState.ACTING)
        elif kind is EventKind.AGENT_SUSPENDED:
            update = replace(update, state=SurfaceState.SUSPENDED)
        elif kind is EventKind.AGENT_RESUMED:
            update = replace(update, state=SurfaceState.ACTING)
        elif kind is EventKind.AO_REQUEST:
            update = replace(update, state=SurfaceState.DELIBERATING)
        elif kind is EventKind.INTENT_DECLARED:
            update = replace(update, state=SurfaceState.ACTING)
            origin, target = _point(payload.get("origin")), _point(payload.get("target"))
            if origin and target:
                update = replace(update, leash=(origin, target))
        elif kind is EventKind.VERIFICATION:
            # A failed verification is the operator's cue to look, so it colours
            # the whole frame rather than scrolling past in the chat panel.
            if payload.get("ok") is False:
                update = replace(update, state=SurfaceState.FAULT)
            update = replace(update, clear_leash=True)
        elif kind in (EventKind.KEY_DOWN, EventKind.KEY_UP):
            key = str(payload.get("key") or payload.get("action") or "").strip()
            if not key:
                return update
            lowered = key.lower()
            if kind is EventKind.KEY_DOWN:
                update = replace(update, flash_key=key)
                if lowered in MODIFIERS:
                    self.held.add(lowered)
            else:
                self.held.discard(lowered)
            update = replace(update, held_keys=frozenset(self.held))
        elif kind is EventKind.POINTER_MOVED:
            point = _point(payload.get("point")) or _point(payload.get("target"))
            synthetic = bool(payload.get("synthetic", True))
            if point:
                update = replace(update, pointer=point, pointer_synthetic=synthetic)
            origin, target = _point(payload.get("origin")), _point(payload.get("target"))
            if origin and target:
                update = replace(update, leash=(origin, target))

        if kind in _CHAT_KINDS:
            update = replace(update, chat_line=_summarise(kind, payload))

        if update.state is not None:
            self.state = update.state
        return update
