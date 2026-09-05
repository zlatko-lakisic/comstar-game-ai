"""The judging half of the Phase 3 acceptance checks.

Collecting the evidence needs a live display; deciding whether the evidence means
pass or fail does not, and that is where the bugs hide — a check that passes when
the overlay never appeared is worse than no check.
"""

from __future__ import annotations

from PIL import Image, ImageDraw

from comstar_game_ai.overlay_ui.checks import (
    capture_exclusion_verdict,
    click_through_verdict,
    non_activation_verdict,
    count_test_pattern_pixels,
)
from comstar_game_ai.overlay_ui.state import TEST_PATTERN_RGB

GAME_HWND = 0x1234
OVERLAY_HWNDS = [0xAAA1, 0xAAA2, 0xAAA3, 0xAAA4, 0xAAA5]


def _clean_frame() -> Image.Image:
    """A plausible campaign frame: earth, sea and a parchment HUD bar."""
    image = Image.new("RGB", (640, 360), (58, 96, 74))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 300, 640, 360), fill=(228, 216, 186))
    draw.rectangle((80, 60, 200, 150), fill=(40, 90, 110))
    return image


def _leaked_frame() -> Image.Image:
    """What a broken SetWindowDisplayAffinity looks like: the glow got captured."""
    image = _clean_frame()
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 640, 6), fill=TEST_PATTERN_RGB)
    return image


# --- capture exclusion -------------------------------------------------------


def test_clean_frame_passes_capture_exclusion():
    outcome = capture_exclusion_verdict(_clean_frame())
    assert outcome.ok
    assert "absent" in outcome.detail


def test_leaked_overlay_fails_capture_exclusion():
    outcome = capture_exclusion_verdict(_leaked_frame())
    assert not outcome.ok
    assert "leaked" in outcome.detail


def test_a_fully_covered_frame_fails():
    solid = Image.new("RGB", (320, 200), TEST_PATTERN_RGB)
    assert not capture_exclusion_verdict(solid).ok


def test_a_handful_of_stray_pixels_is_tolerated():
    """Scaling can smear an unrelated pixel into range; that is not a leak."""
    image = _clean_frame()
    image.putpixel((10, 10), TEST_PATTERN_RGB)
    image.putpixel((11, 10), TEST_PATTERN_RGB)
    assert capture_exclusion_verdict(image).ok


def test_near_misses_count_because_alpha_blending_shifts_the_colour():
    red, green, blue = TEST_PATTERN_RGB
    shifted = (red - 8, min(255, green + 8), blue - 8)
    image = Image.new("RGB", (64, 64), shifted)
    assert count_test_pattern_pixels(image) == 64 * 64
    assert not capture_exclusion_verdict(image).ok


def test_a_merely_reddish_frame_is_not_the_test_pattern():
    """Rome's terracotta roofs must not read as a capture leak."""
    image = Image.new("RGB", (64, 64), (170, 45, 40))
    assert count_test_pattern_pixels(image) == 0


# --- click through -----------------------------------------------------------


def test_click_through_passes_when_every_point_hits_the_game():
    samples = [("EdgeGlowSurface", GAME_HWND), ("StateChipSurface", GAME_HWND)]
    outcome = click_through_verdict(samples, overlay_hwnds=OVERLAY_HWNDS)
    assert outcome.ok


def test_click_through_fails_when_a_surface_owns_the_point():
    samples = [("EdgeGlowSurface", GAME_HWND), ("ChatPanelSurface", OVERLAY_HWNDS[2])]
    outcome = click_through_verdict(samples, overlay_hwnds=OVERLAY_HWNDS)
    assert not outcome.ok
    assert "ChatPanelSurface" in outcome.detail


def test_click_through_names_every_offending_surface():
    samples = [
        ("EdgeGlowSurface", OVERLAY_HWNDS[0]),
        ("KeyboardSurface", OVERLAY_HWNDS[3]),
        ("StateChipSurface", GAME_HWND),
    ]
    detail = click_through_verdict(samples, overlay_hwnds=OVERLAY_HWNDS).detail
    assert "EdgeGlowSurface" in detail and "KeyboardSurface" in detail
    assert "2 of 3" in detail


def test_click_through_fails_when_nothing_was_sampled():
    """An empty sample set means no surface was visible — not a pass."""
    assert not click_through_verdict([], overlay_hwnds=OVERLAY_HWNDS).ok


def test_click_through_fails_when_no_window_owns_the_point():
    samples = [("EdgeGlowSurface", 0)]
    outcome = click_through_verdict(samples, overlay_hwnds=OVERLAY_HWNDS)
    assert not outcome.ok
    assert "reach nothing" in outcome.detail


def test_hitting_a_third_party_window_still_counts_as_click_through():
    """A notification popup over the game is not the overlay's fault."""
    samples = [("EdgeGlowSurface", 0x9999)]
    assert click_through_verdict(samples, overlay_hwnds=OVERLAY_HWNDS).ok


# --- non activation ----------------------------------------------------------


def test_non_activation_passes_when_the_game_kept_focus():
    assert non_activation_verdict(GAME_HWND, GAME_HWND).ok


def test_non_activation_fails_when_a_surface_took_focus():
    outcome = non_activation_verdict(OVERLAY_HWNDS[0], GAME_HWND, overlay_hwnds=OVERLAY_HWNDS)
    assert not outcome.ok
    assert "overlay surface took focus" in outcome.detail


def test_a_third_party_holding_focus_is_reported_as_inconclusive():
    """Launched from a console, the console has focus. Blaming the overlay for
    that sends the reader hunting a bug that is not there."""
    console_hwnd = 0x7777
    outcome = non_activation_verdict(console_hwnd, GAME_HWND, overlay_hwnds=OVERLAY_HWNDS)
    assert not outcome.ok
    assert "neither the game nor the overlay" in outcome.detail
    assert "re-run" in outcome.detail


def test_outcomes_are_truthy_by_ok():
    assert bool(non_activation_verdict(GAME_HWND, GAME_HWND)) is True
    assert bool(non_activation_verdict(1, 2)) is False
