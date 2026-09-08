"""Auto-resolve pointed at the retreat flag.

The Battle Deployment footer holds three evenly spaced discs: a white retreat
flag, crossed swords to fight, and auto-resolve — a screen with circular arrows.
`AUTO_RESOLVE_BUTTON` was 0.43, which is the flag.

So every auto-resolve the campaign ever attempted was a request to withdraw. When
the game refused one — you cannot retreat from a failed ambush — the panel stayed
put, the wait ended at "battle panel did not clear after auto-resolve", and the
loop kept clicking until something started the battle for real. A run then sat
inside that battle, on its pause menu, until it ran out of turns.

The fixture is the real footer at full resolution, cropped to x 0.38-0.62 and
y 0.68-0.78 of a 1920x1080 frame. Downscaling was not an option: the panel
detector's thresholds do not survive it, and quantising it small enough was
unstable — 32 colours passed, 64 failed, which is luck, not a test.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest
from PIL import Image

from comstar_game_ai.game_io.campaign.combat import (
    AUTO_RESOLVE_BUTTON,
    BATTLE_FIGHT_BUTTON,
    BATTLE_RETREAT_BUTTON,
)

FOOTER = pathlib.Path(__file__).parent.parent / "fixtures" / "frames"
CROP_X0, CROP_X1 = 0.38, 0.62
CROP_Y0, CROP_Y1 = 0.68, 0.78


@pytest.fixture
def footer():
    return Image.open(FOOTER / "battle-deployment-footer.png").convert("RGB")


def red_fraction(image, x_norm: float, y_norm: float, radius: int = 20) -> float:
    """How much of the disc under a normalised point is red.

    Coverage rather than the centre pixel: both red discs carry a glyph in the
    middle — silver swords, a gold screen — so sampling dead centre reports the
    glyph and misses the button it sits on.
    """
    w, h = image.size
    x = int((x_norm - CROP_X0) / (CROP_X1 - CROP_X0) * w)
    y = int((y_norm - CROP_Y0) / (CROP_Y1 - CROP_Y0) * h)
    assert 0 <= x < w and 0 <= y < h, f"({x_norm}, {y_norm}) falls outside the crop"

    patch = np.asarray(image)[
        max(0, y - radius) : y + radius, max(0, x - radius) : x + radius
    ].astype(np.int16)
    r, g, b = patch[:, :, 0], patch[:, :, 1], patch[:, :, 2]
    return float(((r > 110) & (r > g + 45) & (r > b + 45)).mean())


def test_auto_resolve_lands_on_the_red_disc(footer):
    """The screen-and-arrows button, not the flag beside it."""
    assert red_fraction(footer, *AUTO_RESOLVE_BUTTON) > 0.4


def test_the_old_coordinate_was_the_retreat_flag(footer):
    """The bug itself: 0.43 is the white flag, and the flag disc is not red."""
    assert red_fraction(footer, 0.43, 0.72) < 0.1, (
        "0.43 is on a red disc, so this test no longer describes the bug"
    )
    assert red_fraction(footer, *BATTLE_RETREAT_BUTTON) < 0.1


def test_the_three_buttons_are_distinct(footer):
    """Retreat, fight and auto-resolve must not collapse onto each other."""
    xs = sorted(x for x, _ in (BATTLE_RETREAT_BUTTON, BATTLE_FIGHT_BUTTON, AUTO_RESOLVE_BUTTON))
    gaps = [b - a for a, b in zip(xs, xs[1:], strict=False)]

    assert all(gap > 0.05 for gap in gaps), f"buttons are too close to tell apart: {gaps}"
    assert red_fraction(footer, *BATTLE_FIGHT_BUTTON) > 0.4, "fight is a red disc too"
