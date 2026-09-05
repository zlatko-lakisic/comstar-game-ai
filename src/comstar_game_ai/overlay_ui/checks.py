"""The three Phase 3 acceptance checks, as pure verdicts.

Gathering the evidence needs a live display, a running game and a live overlay.
Judging the evidence does not, so the judging lives here and is unit tested. The
live harness in `overlay_ui.live_checks` collects facts and hands them over.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import numpy as np

from comstar_game_ai.overlay_ui.state import TEST_PATTERN_RGB


@dataclass(frozen=True)
class CheckOutcome:
    name: str
    ok: bool
    detail: str

    def __bool__(self) -> bool:
        return self.ok


def count_test_pattern_pixels(
    image,
    *,
    rgb: tuple[int, int, int] = TEST_PATTERN_RGB,
    tolerance: int = 24,
) -> int:
    """Pixels within `tolerance` of `rgb` on every channel.

    Tolerance is not paranoia: the overlay is composited with alpha and the
    capture path can go through JPEG-ish scaling, so an exact match would let a
    visible leak pass as clean.
    """
    array = np.asarray(image.convert("RGB"), dtype=np.int16)
    target = np.asarray(rgb, dtype=np.int16)
    near = np.all(np.abs(array - target) <= tolerance, axis=2)
    return int(near.sum())


def capture_exclusion_verdict(
    image,
    *,
    rgb: tuple[int, int, int] = TEST_PATTERN_RGB,
    tolerance: int = 24,
    max_pixels: int = 64,
) -> CheckOutcome:
    """Pass when the overlay's test pattern is absent from the captured frame.

    A handful of stray pixels is allowed because scaling can smear an unrelated
    bright pixel into range; a leaking surface shows up as thousands.
    """
    count = count_test_pattern_pixels(image, rgb=rgb, tolerance=tolerance)
    total = image.size[0] * image.size[1]
    if count > max_pixels:
        return CheckOutcome(
            "capture_exclusion",
            False,
            f"overlay leaked into the capture: {count} of {total} pixels match "
            f"the test pattern {rgb} (allowed {max_pixels})",
        )
    return CheckOutcome(
        "capture_exclusion",
        True,
        f"test pattern absent from a {image.size[0]}x{image.size[1]} frame ({count} stray pixels)",
    )


def click_through_verdict(
    samples: Sequence[tuple[str, int]],
    *,
    overlay_hwnds: Iterable[int],
) -> CheckOutcome:
    """Pass when the OS hit-test at every sampled point misses the overlay.

    WindowFromPoint honours WS_EX_TRANSPARENT, so asking the OS which window
    owns a point *is* the click-through question — and unlike injecting a real
    click it cannot mutate game state, which matters when the acceptance run
    happens on a live campaign.
    """
    if not samples:
        return CheckOutcome("click_through", False, "no surface points were sampled")

    blocked = [(label, hwnd) for label, hwnd in samples if hwnd in set(overlay_hwnds)]
    if blocked:
        listed = ", ".join(f"{label} -> hwnd {hwnd}" for label, hwnd in blocked)
        return CheckOutcome(
            "click_through",
            False,
            f"{len(blocked)} of {len(samples)} sampled points hit an overlay surface: {listed}",
        )

    missing = [label for label, hwnd in samples if not hwnd]
    if missing:
        return CheckOutcome(
            "click_through",
            False,
            f"no window owns {', '.join(missing)} — a click there would reach nothing",
        )

    return CheckOutcome(
        "click_through",
        True,
        f"all {len(samples)} sampled surface points hit through to the window beneath",
    )


def non_activation_verdict(
    foreground_hwnd: int,
    game_hwnd: int,
    *,
    overlay_hwnds: Iterable[int] = (),
) -> CheckOutcome:
    """Pass when showing the overlay left the game in the foreground.

    Three outcomes, not two. If something that is neither the game nor an overlay
    surface holds focus — the console this was launched from, most likely — then
    the check proves nothing, and saying "the overlay stole focus" would send the
    reader hunting a bug that is not there.
    """
    if foreground_hwnd == game_hwnd:
        return CheckOutcome("non_activation", True, f"game hwnd {game_hwnd} still foreground")

    if foreground_hwnd in set(overlay_hwnds):
        return CheckOutcome(
            "non_activation",
            False,
            f"an overlay surface took focus from the game: hwnd {foreground_hwnd} "
            f"is a surface, expected game hwnd {game_hwnd}",
        )

    return CheckOutcome(
        "non_activation",
        False,
        f"neither the game nor the overlay has focus (hwnd {foreground_hwnd}); the game "
        f"must be the foreground window for this check to mean anything — click the game "
        f"during the countdown and re-run",
    )
