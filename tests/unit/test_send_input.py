"""Tests for the synthetic input layer.

These cover a bug that was invisible for the whole of Phase 2: `tap_key` sent a
virtual-key event carrying no scancode. SendInput accepts it and returns success,
ordinary windows receive it, and Rome -- which reads the keyboard through
DirectInput -- ignores it completely. So every unmodified keypress silently did
nothing while every API call reported it had worked, and the conclusion drawn at the
time was that panels ignore Escape. They do not; Escape was never arriving.

The assertions therefore inspect the INPUT structures actually handed to SendInput,
because the return value cannot distinguish a delivered key from a dropped one.
"""

import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="win32 input layer")

from comstar_game_ai.game_io.input.send_input import (  # noqa: E402
    SendInputController,
    normalize_key_name,
    virtual_key_for,
)


@pytest.fixture
def recorded(monkeypatch):
    """Capture every INPUT struct passed to SendInput instead of sending it."""
    import ctypes

    from comstar_game_ai.game_io.input import send_input as si

    sent = []

    def fake_send_input(count, array, size):
        struct = ctypes.cast(array, ctypes.POINTER(si.INPUT)).contents
        if struct.type == si.INPUT_KEYBOARD:
            key = struct.union.ki
            sent.append({
                "kind": "key",
                "vk": key.wVk,
                "scan": key.wScan,
                "flags": key.dwFlags,
                "up": bool(key.dwFlags & si.KEYEVENTF_KEYUP),
                "scancode_flag": bool(key.dwFlags & si.KEYEVENTF_SCANCODE),
                "extended": bool(key.dwFlags & si.KEYEVENTF_EXTENDEDKEY),
            })
        else:
            mouse = struct.union.mi
            sent.append({
                "kind": "mouse",
                "dx": mouse.dx,
                "dy": mouse.dy,
                "flags": mouse.dwFlags,
                "virtualdesk": bool(mouse.dwFlags & si.MOUSEEVENTF_VIRTUALDESK),
            })
        return 1

    controller = SendInputController()
    monkeypatch.setattr(controller._user32, "SendInput", fake_send_input, raising=False)
    return controller, sent


def key_events(sent):
    """Just the keystrokes, dropping the modifier releases tap_key opens with."""
    return [e for e in sent if e["kind"] == "key"]


# --- The scancode regression -------------------------------------------------


def test_tap_key_sends_a_scancode_not_a_bare_virtual_key(recorded):
    controller, sent = recorded
    assert controller.tap_key("z")

    presses = [e for e in key_events(sent) if e["scan"] == controller.scancode_for("z")[0]]
    assert presses, "no event carried z's scancode"
    for event in presses:
        assert event["scancode_flag"], "KEYEVENTF_SCANCODE missing; DirectInput ignores it"
        assert event["vk"] == 0, "a scancode event must not also carry a virtual key"
        assert event["scan"] != 0


def test_tap_key_sends_both_a_press_and_a_release(recorded):
    controller, sent = recorded
    scan = controller.scancode_for("z")[0]
    controller.tap_key("z")

    ours = [e for e in key_events(sent) if e["scan"] == scan]
    assert [e["up"] for e in ours] == [False, True]


def test_no_key_event_is_ever_sent_without_a_scancode(recorded):
    """The exact shape of the original bug, asserted globally."""
    controller, sent = recorded
    for key in ("escape", "tab", "z", "home", "f1", "5"):
        assert controller.tap_key(key)

    for event in key_events(sent):
        assert event["scancode_flag"] and event["scan"] != 0, (
            "a virtual-key-only event reached SendInput; it would be silently dropped"
        )


def test_chord_sends_modifier_around_the_key(recorded):
    controller, sent = recorded
    ctrl_scan = controller.scancode_for("ctrl")[0]
    four_scan = controller.scancode_for("4")[0]
    assert controller.chord_scancode("ctrl", "4")

    order = [(e["scan"], e["up"]) for e in key_events(sent)
             if e["scan"] in (ctrl_scan, four_scan)]
    # The modifier has to be down before the key and released after it, or the game
    # sees a bare '4'.
    assert order[-4:] == [
        (ctrl_scan, False), (four_scan, False), (four_scan, True), (ctrl_scan, True),
    ]


# --- Extended keys -----------------------------------------------------------


@pytest.mark.parametrize("key", ["home", "pageup", "left", "delete"])
def test_navigation_keys_are_marked_extended(recorded, key):
    controller, sent = recorded
    assert controller.tap_key(key)
    scan = controller.scancode_for(key)[0]
    ours = [e for e in key_events(sent) if e["scan"] == scan]
    assert ours
    for event in ours:
        # Without the flag the same scancode addresses the numeric keypad instead.
        assert event["extended"], "%s needs KEYEVENTF_EXTENDEDKEY" % key


@pytest.mark.parametrize("key", ["z", "5", "escape", "tab", "f1"])
def test_ordinary_keys_are_not_marked_extended(recorded, key):
    controller, sent = recorded
    assert controller.tap_key(key)
    scan = controller.scancode_for(key)[0]
    for event in [e for e in key_events(sent) if e["scan"] == scan]:
        assert not event["extended"]


def test_camera_and_panel_keys_all_resolve_to_a_scancode():
    controller = SendInputController()
    # Every key the campaign atlas and the camera bindings actually need.
    for key in ("w", "a", "s", "d", "q", "e", "z", "x", "home", "pageup",
                "tab", "escape", "shift", "ctrl", "1", "7", "f1", "5", "6", "b", "r"):
        assert controller.scancode_for(key) is not None, key


def test_home_and_pageup_have_virtual_keys_at_all():
    # They were absent from the map, so camera actions bound to them resolved to
    # None and the binding was unreachable rather than merely mis-sent.
    assert virtual_key_for("home") is not None
    assert virtual_key_for("pageup") is not None


def test_unknown_key_is_refused_rather_than_guessed(recorded):
    controller, sent = recorded
    assert controller.tap_key("no_such_key") is False
    assert controller.scancode_for("no_such_key") is None


def test_key_names_are_case_insensitive():
    assert normalize_key_name(" Escape ") == "escape"
    controller = SendInputController()
    assert controller.scancode_for("ESCAPE") == controller.scancode_for("escape")


# --- Mouse -------------------------------------------------------------------


def test_move_mouse_addresses_the_whole_virtual_desktop(recorded):
    controller, sent = recorded
    assert controller.move_mouse(2934, 336)
    moves = [e for e in sent if e["kind"] == "mouse"]
    assert moves and moves[-1]["virtualdesk"], (
        "without MOUSEEVENTF_VIRTUALDESK, absolute coordinates address only the "
        "primary monitor and a window on any other monitor is unclickable"
    )


def test_click_reasserts_position_before_pressing(recorded):
    """Rome samples the cursor on its own tick, so a press must follow a settled move.

    The symptom of getting this wrong is a hover tooltip appearing under the target
    while the click does nothing at all.
    """
    controller, sent = recorded
    assert controller.click(100, 100, dwell_ms=1, settle_ms=1)

    kinds = [e["flags"] for e in sent if e["kind"] == "mouse"]
    import comstar_game_ai.game_io.input.send_input as si

    moves = [f for f in kinds if f & si.MOUSEEVENTF_MOVE]
    downs = [f for f in kinds if f & si.MOUSEEVENTF_LEFTDOWN]
    ups = [f for f in kinds if f & si.MOUSEEVENTF_LEFTUP]
    assert len(moves) >= 2, "the move is sent twice so it cannot be coalesced away"
    assert len(downs) == 1 and len(ups) == 1
    # And the press must come after every move.
    assert kinds.index(downs[0]) > kinds.index(moves[-1])
