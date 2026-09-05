"""Render the real surfaces offscreen.

Qt's offscreen platform gives genuine painting without touching the display, so
this catches the failures that unit-testing the router cannot: a paintEvent that
throws, a surface that never sizes itself, or an edge glow that draws the wrong
state colour. What it cannot check is window styles and capture exclusion, which
need a real compositor — those are `comstar-overlay --self-test`.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6", reason="overlay needs PySide6")

from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from comstar_game_ai.overlay_ui.main import apply_update  # noqa: E402
from comstar_game_ai.overlay_ui.router import EventRouter  # noqa: E402
from comstar_game_ai.overlay_ui.state import (  # noqa: E402
    TEST_PATTERN_RGB,
    STATE_COLOURS,
    SurfaceState,
)
from comstar_game_ai.overlay_ui.surfaces import OverlaySurfaces  # noqa: E402
from comstar_game_ai.shared.ipc.events import EventKind  # noqa: E402

NO_GAME_WINDOW = 0


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def surfaces(app):
    # A huge sync interval keeps the geometry timer from firing mid-test.
    made = OverlaySurfaces(NO_GAME_WINDOW, sync_ms=10_000_000)
    yield made
    made.close_all()


def _render(surface, width: int = 400, height: int = 300) -> QImage:
    surface.resize(max(surface.width(), width), max(surface.height(), height))
    image = QImage(surface.size(), QImage.Format.Format_ARGB32)
    image.fill(0)
    surface.render(image)
    return image


def _pixels(image: QImage) -> set[tuple[int, int, int]]:
    return {
        image.pixelColor(x, y).getRgb()[:3]
        for x in range(0, image.width(), 3)
        for y in range(0, image.height(), 3)
        if image.pixelColor(x, y).alpha() > 40
    }


def test_all_five_surfaces_exist(surfaces):
    names = [type(surface).__name__ for surface in surfaces.surfaces]
    assert names == [
        "EdgeGlowSurface",
        "StateChipSurface",
        "ChatPanelSurface",
        "KeyboardSurface",
        "CursorLeashSurface",
    ]


def test_every_surface_paints_without_raising(surfaces):
    for surface in surfaces.surfaces:
        _render(surface)


def test_hwnds_are_reported_for_the_click_through_check(surfaces):
    assert len(surfaces.hwnds()) == len(surfaces.surfaces)


def test_glow_and_chip_never_disagree(surfaces):
    surfaces.set_state("handing_back")
    assert surfaces.glow.state is SurfaceState.SUSPENDED
    assert surfaces.state.state is SurfaceState.SUSPENDED


@pytest.mark.parametrize("state", list(SurfaceState), ids=lambda s: s.value)
def test_the_glow_paints_the_colour_of_its_state(surfaces, state):
    """The colour *is* the message, so assert the pixels, not the attribute."""
    surfaces.glow.set_state(state)
    painted = _pixels(_render(surfaces.glow))
    expected = STATE_COLOURS[state]

    def close(found: tuple[int, int, int]) -> bool:
        return all(abs(a - b) <= 12 for a, b in zip(found, expected))

    assert any(close(colour) for colour in painted), f"{state.value} glow never painted {expected}"


def test_the_glow_does_not_paint_over_the_map(surfaces):
    """A filled glow would hide the game; only the border and brackets may paint."""
    surfaces.glow.set_state(SurfaceState.ACTING)
    image = _render(surfaces.glow, 400, 300)
    centre = image.pixelColor(image.width() // 2, image.height() // 2)
    assert centre.alpha() == 0, "the edge glow filled the middle of the screen"


def test_test_pattern_mode_covers_the_frame(app):
    """The capture-exclusion self test is only meaningful if this really paints."""
    surfaces = OverlaySurfaces(NO_GAME_WINDOW, test_pattern=True, sync_ms=10_000_000)
    try:
        image = _render(surfaces.glow, 200, 150)
        assert image.pixelColor(100, 75).getRgb()[:3] == TEST_PATTERN_RGB
        assert image.pixelColor(2, 2).getRgb()[:3] == TEST_PATTERN_RGB
    finally:
        surfaces.close_all()


def test_normal_mode_never_paints_the_test_pattern(surfaces):
    surfaces.glow.set_state(SurfaceState.DELIBERATING)
    assert TEST_PATTERN_RGB not in _pixels(_render(surfaces.glow))


def test_keyboard_lights_a_held_modifier(surfaces):
    before = _pixels(_render(surfaces.keyboard))
    surfaces.keyboard.set_held({"ctrl"})
    after = _pixels(_render(surfaces.keyboard))
    assert after != before, "holding Ctrl changed nothing on screen"


def test_keyboard_starts_faded_and_lights_up_on_a_press(surfaces):
    assert surfaces.keyboard.windowOpacity() == pytest.approx(
        surfaces.keyboard.IDLE_OPACITY, abs=0.01
    )
    surfaces.keyboard.flash_key("2")
    assert surfaces.keyboard.windowOpacity() == pytest.approx(
        surfaces.keyboard.ACTIVE_OPACITY, abs=0.01
    )


def test_the_leash_marks_the_destination_before_the_cursor_travels(surfaces):
    surfaces.leash.set_leash((20, 20), (300, 200))
    painted = _pixels(_render(surfaces.leash))
    assert painted, "leash drew nothing"


def test_synthetic_and_human_pointers_are_different_colours(surfaces):
    surfaces.leash.set_pointer((200, 150), synthetic=True)
    synthetic = _pixels(_render(surfaces.leash))
    surfaces.leash.set_pointer((200, 150), synthetic=False)
    human = _pixels(_render(surfaces.leash))
    assert synthetic != human


def test_a_full_event_sequence_drives_the_surfaces(surfaces):
    """The path a real session takes, through the code main.py actually runs."""
    router = EventRouter()
    sequence = [
        (EventKind.CONTROL_STATE, {"state": "agent"}),
        (EventKind.FREEZE, {}),
        (EventKind.AO_REQUEST, {"summary": "battle directive"}),
        (EventKind.AO_STATUS, {"phase": "deliberating", "queue_position": 2}),
        (EventKind.INTENT_DECLARED, {"summary": "flank right", "origin": [10, 20], "target": [400, 300]}),
        (EventKind.KEY_DOWN, {"key": "Ctrl"}),
        (EventKind.KEY_DOWN, {"key": "2"}),
        (EventKind.POINTER_MOVED, {"point": [300, 200]}),
        (EventKind.KEY_UP, {"key": "Ctrl"}),
        (EventKind.VERIFICATION, {"ok": True, "summary": "unit moved"}),
    ]
    for kind, payload in sequence:
        apply_update(surfaces, router.route(kind, payload))

    assert surfaces.glow.state is SurfaceState.ACTING
    for surface in surfaces.surfaces:
        _render(surface)


def test_a_failed_verification_turns_the_frame_red(surfaces):
    router = EventRouter()
    apply_update(surfaces, router.route(EventKind.CONTROL_STATE, {"state": "agent"}))
    apply_update(surfaces, router.route(EventKind.VERIFICATION, {"ok": False, "summary": "stuck"}))
    assert surfaces.glow.state is SurfaceState.FAULT
    painted = _pixels(_render(surfaces.glow))
    fault = STATE_COLOURS[SurfaceState.FAULT]
    assert any(all(abs(a - b) <= 12 for a, b in zip(colour, fault)) for colour in painted)
