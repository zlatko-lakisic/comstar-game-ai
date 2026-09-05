"""The overlay's semantics: which event means what on screen."""

from __future__ import annotations

import pytest

from comstar_game_ai.overlay_ui.router import MODIFIERS, EventRouter
from comstar_game_ai.overlay_ui.state import (
    STATE_COLOURS,
    STATE_LABELS,
    SurfaceState,
    coerce_state,
    state_colour,
    state_label,
)
from comstar_game_ai.shared.ipc.events import EventKind


# --- state vocabulary --------------------------------------------------------


def test_every_state_has_a_colour_and_a_label():
    for state in SurfaceState:
        assert state in STATE_COLOURS
        assert state in STATE_LABELS


def test_colours_match_the_mockup_legend():
    """docs/images/overlay-mockup.html is the reference the operator learned."""
    assert STATE_COLOURS[SurfaceState.DELIBERATING] == (0x5F, 0xD0, 0xE0)
    assert STATE_COLOURS[SurfaceState.ACTING] == (0x7F, 0xC0, 0x8A)
    assert STATE_COLOURS[SurfaceState.SUSPENDED] == (0xE8, 0xA3, 0x3D)
    assert STATE_COLOURS[SurfaceState.FAULT] == (0xE0, 0x68, 0x5F)
    assert STATE_COLOURS[SurfaceState.IDLE] == (0x8D, 0x9A, 0xA2)


def test_every_state_is_a_distinct_colour():
    """Two states that look alike are worse than one state."""
    assert len(set(STATE_COLOURS.values())) == len(SurfaceState)


@pytest.mark.parametrize(
    ("control_mode", "expected"),
    [
        ("idle", SurfaceState.IDLE),
        ("agent", SurfaceState.ACTING),
        ("handing_back", SurfaceState.SUSPENDED),
        ("killed", SurfaceState.FAULT),
    ],
)
def test_control_modes_map_onto_surface_states(control_mode, expected):
    """Process A publishes ControlMode; the overlay must understand all of them."""
    assert coerce_state(control_mode) is expected


def test_control_mode_members_are_all_covered():
    from comstar_game_ai.game_io.safety import ControlMode

    for mode in ControlMode:
        assert coerce_state(mode.value) is not None


def test_unknown_state_falls_back_to_idle_instead_of_raising():
    """The overlay may not crash Process A's stream over a new state name."""
    assert coerce_state("transcendent") is SurfaceState.IDLE
    assert coerce_state(None) is SurfaceState.IDLE
    assert coerce_state("") is SurfaceState.IDLE
    assert state_colour("nonsense") == STATE_COLOURS[SurfaceState.IDLE]
    assert state_label("nonsense") == STATE_LABELS[SurfaceState.IDLE]


def test_states_can_be_named_directly_too():
    assert coerce_state("deliberating") is SurfaceState.DELIBERATING
    assert coerce_state(SurfaceState.FAULT) is SurfaceState.FAULT
    assert coerce_state("ACTING") is SurfaceState.ACTING


# --- routing -----------------------------------------------------------------


def test_control_state_event_sets_the_state():
    router = EventRouter()
    assert router.route(EventKind.CONTROL_STATE, {"state": "agent"}).state is SurfaceState.ACTING
    assert router.state is SurfaceState.ACTING


def test_freeze_reads_as_deliberating_and_resume_as_acting():
    """The battle loop freezes the game so the agent can think; say so."""
    router = EventRouter()
    assert router.route(EventKind.FREEZE, {}).state is SurfaceState.DELIBERATING
    assert router.route(EventKind.RESUME, {}).state is SurfaceState.ACTING


def test_ao_request_shows_deliberating_and_logs_a_line():
    router = EventRouter()
    update = router.route(EventKind.AO_REQUEST, {"summary": "battle directive"})
    assert update.state is SurfaceState.DELIBERATING
    assert "battle directive" in update.chat_line


def test_suspend_and_resume_move_the_glow():
    router = EventRouter()
    assert router.route(EventKind.AGENT_SUSPENDED, {}).state is SurfaceState.SUSPENDED
    assert router.route(EventKind.AGENT_RESUMED, {}).state is SurfaceState.ACTING


def test_failed_verification_raises_a_fault():
    router = EventRouter()
    update = router.route(EventKind.VERIFICATION, {"ok": False, "summary": "unit never moved"})
    assert update.state is SurfaceState.FAULT
    assert "failed" in update.chat_line


def test_passing_verification_does_not_change_state():
    router = EventRouter()
    router.route(EventKind.CONTROL_STATE, {"state": "agent"})
    update = router.route(EventKind.VERIFICATION, {"ok": True, "summary": "moved"})
    assert update.state is None
    assert router.state is SurfaceState.ACTING


def test_verification_clears_the_leash():
    """The proposed click has happened and been judged; stop advertising it."""
    router = EventRouter()
    assert router.route(EventKind.VERIFICATION, {"ok": True}).clear_leash


def test_ao_status_summarises_queue_position_phase_and_latency():
    router = EventRouter()
    line = router.route(
        EventKind.AO_STATUS, {"phase": "deliberating", "queue_position": 3, "latency_ms": 1840}
    ).chat_line
    assert "deliberating" in line and "queue #3" in line and "1840 ms" in line


def test_ao_status_accepts_camel_case_from_the_reach_bridge():
    router = EventRouter()
    line = router.route(EventKind.AO_STATUS, {"phase": "queued", "queuePosition": 1}).chat_line
    assert "queue #1" in line


def test_intent_declared_draws_the_leash_before_the_cursor_travels():
    router = EventRouter()
    update = router.route(
        EventKind.INTENT_DECLARED, {"summary": "flank right", "origin": [10, 20], "target": [300, 400]}
    )
    assert update.leash == ((10, 20), (300, 400))
    assert update.state is SurfaceState.ACTING


def test_intent_without_coordinates_still_logs():
    router = EventRouter()
    update = router.route(EventKind.INTENT_DECLARED, {"summary": "hold the line"})
    assert update.leash is None
    assert "hold the line" in update.chat_line


@pytest.mark.parametrize("modifier", sorted(MODIFIERS))
def test_held_modifiers_stay_lit_until_released(modifier):
    router = EventRouter()
    down = router.route(EventKind.KEY_DOWN, {"key": modifier})
    assert down.flash_key == modifier
    assert down.held_keys == frozenset({modifier})
    up = router.route(EventKind.KEY_UP, {"key": modifier})
    assert up.held_keys == frozenset()


def test_plain_keys_flash_but_are_not_held():
    """Ctrl held is what makes 2 mean group two; a held 2 is meaningless."""
    router = EventRouter()
    update = router.route(EventKind.KEY_DOWN, {"key": "2"})
    assert update.flash_key == "2"
    assert update.held_keys == frozenset()


def test_a_modifier_survives_other_keypresses():
    router = EventRouter()
    router.route(EventKind.KEY_DOWN, {"key": "Ctrl"})
    update = router.route(EventKind.KEY_DOWN, {"key": "3"})
    assert update.held_keys == frozenset({"ctrl"})


def test_key_up_for_something_never_pressed_is_harmless():
    router = EventRouter()
    assert router.route(EventKind.KEY_UP, {"key": "shift"}).held_keys == frozenset()


def test_key_events_accept_the_action_field_process_a_actually_sends():
    """runtime.py publishes KEY_DOWN with `action`, not `key`."""
    router = EventRouter()
    assert router.route(EventKind.KEY_DOWN, {"action": "select_group", "unit": 2}).flash_key


def test_pointer_moved_updates_the_ring():
    router = EventRouter()
    update = router.route(EventKind.POINTER_MOVED, {"point": [640, 360]})
    assert update.pointer == (640, 360)
    assert update.pointer_synthetic is True


def test_human_pointer_motion_is_flagged_as_human():
    """Different colour for synthetic and human is the point of the surface."""
    router = EventRouter()
    update = router.route(EventKind.POINTER_MOVED, {"point": [1, 2], "synthetic": False})
    assert update.pointer_synthetic is False


def test_malformed_payloads_do_not_raise():
    router = EventRouter()
    for payload in ({"point": "nowhere"}, {"point": [None, 2]}, {"origin": [1]}, {}):
        assert router.route(EventKind.POINTER_MOVED, payload) is not None


def test_unknown_event_kind_is_ignored_quietly():
    router = EventRouter()
    update = router.route("something_new_from_process_b", {"x": 1})
    assert update.state is None and update.chat_line is None


def test_none_payload_is_survivable():
    router = EventRouter()
    assert router.route(EventKind.CONTROL_STATE, None).state is SurfaceState.IDLE


def test_every_event_kind_is_routable_without_raising():
    """Process A and B may publish any member; none may crash the overlay."""
    router = EventRouter()
    for kind in EventKind:
        assert router.route(kind, {}) is not None
