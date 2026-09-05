"""Phase 3 acceptance harness: the three self tests, run against the full overlay.

Phase 0 ran these against a single stub window (`game_io.overlay_stub`). Phase 3
requires them against every real surface at once, because the failure modes are
per-window: one surface missing WS_EX_TRANSPARENT swallows clicks, and one
surface missing display affinity poisons every frame the agent sees.

Needs a live display, a running game and a real overlay, so it is driven from the
CLI (`comstar-overlay --self-test`) rather than from pytest. The judging lives in
`overlay_ui.checks` and is unit tested there.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field

from comstar_game_ai.overlay_ui.checks import (
    CheckOutcome,
    capture_exclusion_verdict,
    click_through_verdict,
    non_activation_verdict,
)
from comstar_game_ai.overlay_ui.win32_styles import (
    describe_styles,
    foreground_window,
    missing_styles,
    window_from_point,
)

#: Long enough for the compositor to actually paint the surfaces before the
#: capture is taken. Grabbing immediately after show() can catch an empty frame
#: and pass capture exclusion for the wrong reason.
SETTLE_MS = 700


@dataclass
class OverlaySelfTestReport:
    ok: bool = True
    outcomes: list[CheckOutcome] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)

    def record(self, outcome: CheckOutcome) -> None:
        self.outcomes.append(outcome)
        if not outcome.ok:
            self.ok = False

    def fail(self, message: str) -> None:
        self.ok = False
        self.messages.append(message)

    @property
    def tests(self) -> dict[str, bool]:
        return {outcome.name: outcome.ok for outcome in self.outcomes}

    def render(self) -> str:
        lines = [
            f"{'PASS' if outcome.ok else 'FAIL'}  {outcome.name}: {outcome.detail}"
            for outcome in self.outcomes
        ]
        lines.extend(f"NOTE  {message}" for message in self.messages)
        lines.append(f"{'PASS' if self.ok else 'FAIL'}  overlay self tests")
        return "\n".join(lines)


def _sample_points(surfaces) -> list[tuple[str, tuple[int, int]]]:
    """One screen point at the centre of each visible surface.

    Centres, not corners: a corner can fall outside a rounded or inset surface
    and pass the click-through check without ever testing the surface.
    """
    points: list[tuple[str, tuple[int, int]]] = []
    for surface in surfaces.surfaces:
        if not surface.isVisible():
            continue
        geometry = surface.geometry()
        if geometry.width() <= 0 or geometry.height() <= 0:
            continue
        points.append(
            (
                type(surface).__name__,
                (geometry.center().x(), geometry.center().y()),
            )
        )
    # The edge glow spans the whole client area, so its centre sits over the map
    # rather than over the glow's own stroke. Sample the stroke itself as well.
    glow = surfaces.glow.geometry()
    if glow.width() > 0:
        inset = max(2, surfaces.glow.BORDER_WIDTH // 2)
        points.append(("EdgeGlowSurface:top-edge", (glow.center().x(), glow.top() + inset)))
        points.append(("EdgeGlowSurface:left-edge", (glow.left() + inset, glow.center().y())))
    return points


def _style_outcome(surfaces) -> CheckOutcome:
    """Styles are checked directly as well as behaviourally.

    A behavioural pass can happen for the wrong reason — a surface that failed to
    show is trivially click-through — so assert the flags are really set.
    """
    problems: list[str] = []
    for surface, report in zip(surfaces.surfaces, surfaces.style_reports, strict=False):
        name = type(surface).__name__
        if report is None:
            problems.append(f"{name}: styling did not run")
            continue
        if not report.capture_excluded:
            problems.append(f"{name}: SetWindowDisplayAffinity failed ({report.detail})")
        absent = missing_styles(int(surface.winId()))
        if absent:
            problems.append(f"{name}: missing {describe_styles(absent)}")
    if problems:
        return CheckOutcome("overlay_window_styles", False, "; ".join(problems))
    count = len(surfaces.surfaces)
    return CheckOutcome(
        "overlay_window_styles",
        True,
        f"all {count} surfaces are layered, click-through, non-activating and capture-excluded",
    )


def countdown(seconds: int) -> None:
    """Give the operator time to focus the game before anything is measured.

    Launched from a console, the console holds focus, and the non-activation check
    would then be answered about the console rather than the game. Phase 2's live
    script learned the same lesson.
    """
    if seconds <= 0:
        return
    print(f"click the game window and leave it focused — starting in {seconds}s", flush=True)
    for remaining in range(seconds, 0, -1):
        print(f"  {remaining}...", flush=True)
        time.sleep(1)


def run_overlay_self_tests(
    *, settle_ms: int = SETTLE_MS, countdown_seconds: int = 5
) -> OverlaySelfTestReport:
    report = OverlaySelfTestReport()
    if sys.platform != "win32":
        report.fail("Windows required")
        return report

    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication

    from comstar_game_ai.game_io.campaign.ui_mode import grab_rgb_image
    from comstar_game_ai.game_io.window import find_game_window
    from comstar_game_ai.overlay_ui.surfaces import OverlaySurfaces
    from comstar_game_ai.shared.config import load_config

    config = load_config()
    substrings = config.get("game", {}).get("window_title_substrings") or ["Rome"]
    game = find_game_window(substrings)
    if game is None:
        report.fail("no game window found — start the game and load a campaign, then re-run")
        return report

    countdown(countdown_seconds)

    app = QApplication.instance() or QApplication(sys.argv)
    # Test-pattern mode fills the client area with a colour the game never
    # produces, so capture exclusion is proved rather than assumed.
    surfaces = OverlaySurfaces(game.hwnd, test_pattern=True)
    try:
        surfaces.show_all()
        loop = QEventLoop()
        QTimer.singleShot(settle_ms, loop.quit)
        loop.exec()
        app.processEvents()

        overlay_hwnds = surfaces.hwnds()
        report.record(_style_outcome(surfaces))
        report.record(
            non_activation_verdict(foreground_window(), game.hwnd, overlay_hwnds=overlay_hwnds)
        )

        samples = [
            (label, window_from_point(x, y)) for label, (x, y) in _sample_points(surfaces)
        ]
        report.record(click_through_verdict(samples, overlay_hwnds=overlay_hwnds))

        frame = grab_rgb_image(game.hwnd)
        if frame is None:
            report.fail("capture returned nothing, so capture exclusion could not be judged")
        else:
            report.record(capture_exclusion_verdict(frame))
    finally:
        surfaces.close_all()
        app.processEvents()

    return report
