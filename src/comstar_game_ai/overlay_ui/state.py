"""Overlay state vocabulary and palette.

Deliberately free of Qt and win32 imports so the state machine can be tested
without a display. The colours are the ones in docs/images/overlay-mockup.html.
"""

from __future__ import annotations

from enum import Enum


class SurfaceState(str, Enum):
    """What the edge glow and chip are saying, per docs/design/host-overlay-ui.md."""

    IDLE = "idle"
    DELIBERATING = "deliberating"
    ACTING = "acting"
    SUSPENDED = "suspended"
    FAULT = "fault"


#: RGB straight from the mockup legend.
STATE_COLOURS: dict[SurfaceState, tuple[int, int, int]] = {
    SurfaceState.DELIBERATING: (0x5F, 0xD0, 0xE0),
    SurfaceState.ACTING: (0x7F, 0xC0, 0x8A),
    SurfaceState.SUSPENDED: (0xE8, 0xA3, 0x3D),
    SurfaceState.FAULT: (0xE0, 0x68, 0x5F),
    SurfaceState.IDLE: (0x8D, 0x9A, 0xA2),
}

#: Human-readable chip text. "Frozen · deliberating" in the mockup.
STATE_LABELS: dict[SurfaceState, str] = {
    SurfaceState.IDLE: "Idle",
    SurfaceState.DELIBERATING: "Frozen · deliberating",
    SurfaceState.ACTING: "Acting",
    SurfaceState.SUSPENDED: "Suspended",
    SurfaceState.FAULT: "Fault",
}

#: Process A publishes ControlMode values; the overlay speaks SurfaceState.
#: handing_back is shown as suspended because the agent has stopped acting but
#: has not yet released, which is exactly what an operator needs to see.
_CONTROL_MODE_TO_STATE: dict[str, SurfaceState] = {
    "idle": SurfaceState.IDLE,
    "agent": SurfaceState.ACTING,
    "handing_back": SurfaceState.SUSPENDED,
    "killed": SurfaceState.FAULT,
}


def coerce_state(value: object) -> SurfaceState:
    """Best-effort map of anything Process A sends onto a SurfaceState.

    The overlay is allowed to crash but must never crash Process A, and an
    unknown state is not worth dying over: fall back to IDLE.
    """
    if isinstance(value, SurfaceState):
        return value
    text = str(value or "").strip().lower()
    if not text:
        return SurfaceState.IDLE
    if text in _CONTROL_MODE_TO_STATE:
        return _CONTROL_MODE_TO_STATE[text]
    try:
        return SurfaceState(text)
    except ValueError:
        return SurfaceState.IDLE


def state_colour(state: object) -> tuple[int, int, int]:
    return STATE_COLOURS[coerce_state(state)]


def state_label(state: object) -> str:
    return STATE_LABELS[coerce_state(state)]


#: The capture-exclusion self test paints this colour over the game and then
#: asserts it is absent from the captured frame. It has to be a colour the game
#: itself will not produce: Rome's palette is earth, sea and parchment, so a
#: saturated near-magenta never occurs naturally.
TEST_PATTERN_RGB: tuple[int, int, int] = (0xFD, 0x07, 0xFB)
