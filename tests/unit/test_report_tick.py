"""The report scroll's tick, and the pause menu the loop opens on itself.

An unattended run burned all twenty of its turns alternating between these two.
A battle report was on screen; it has no close X and no accept/reject pair, so
the chain fell through to Escape — which does not dismiss a report, but does
open the pause menu when it reaches the map. The next round saw the menu, called
it an unknown panel, pressed Escape, closed it, saw the report again, and went
round once more. Twenty readiness timeouts, zero turns advanced.
"""

from pathlib import Path

import pytest
from PIL import Image

from comstar_game_ai.game_io.campaign.modal import (
    localize_report_confirm_tick,
    pause_menu_present,
)

FRAMES = Path(__file__).resolve().parents[1] / "fixtures" / "frames"


def _frame(name: str) -> Image.Image:
    path = FRAMES / name
    if not path.exists():
        pytest.skip(f"missing frame fixture {name}")
    return Image.open(path).convert("RGB")


def test_the_tick_on_a_battle_report_is_found():
    """A real "AVERAGE VICTORY" scroll, captured mid-run."""
    tick = localize_report_confirm_tick(_frame("report-scroll-average-victory.png"))
    assert tick is not None, "the report's only control went unfound"
    # Centred on the panel, on its bottom rail.
    assert tick.x_norm == pytest.approx(0.50, abs=0.02)
    assert tick.y_norm == pytest.approx(0.93, abs=0.03)


def test_the_clear_map_offers_no_tick():
    """Nothing to acknowledge, so nothing to click."""
    assert localize_report_confirm_tick(_frame("campaign-map-clear.png")) is None


def test_a_floating_notice_offers_no_tick():
    """The faction-destroyed scroll is closed by its corner X, not a tick."""
    frame = _frame("floating-notice-faction-destroyed.png")
    assert localize_report_confirm_tick(frame) is None


def test_the_pause_menu_is_recognized():
    assert pause_menu_present(_frame("campaign-pause-menu.png")) is True


def test_the_clear_map_is_not_the_pause_menu():
    assert pause_menu_present(_frame("campaign-map-clear.png")) is False


def test_a_report_is_not_the_pause_menu():
    assert pause_menu_present(_frame("report-scroll-average-victory.png")) is False


def test_the_pause_menu_offers_no_tick():
    """The menu is panel-wide with grey text low down, so the tick search has to
    refuse it explicitly. It found a "tick" at x 0.67 before this guard — a click
    into empty banner, which changes nothing and leaves the loop where it was."""
    assert localize_report_confirm_tick(_frame("campaign-pause-menu.png")) is None


def test_the_handler_escapes_the_pause_menu_instead_of_hunting_buttons(monkeypatch):
    """One Escape, no clicks, no vision call.

    The menu is the one panel where a click is the wrong move: its buttons quit
    the game or load a save. Escape is both what opened it and what closes it.
    """
    from comstar_game_ai.game_io.campaign import modal as mod
    from comstar_game_ai.game_io.campaign.ui_mode import CampaignUiMode, UiClassification

    menu = _frame("campaign-pause-menu.png")
    handler = mod.ModalHandler(settle_s=0.0, use_ada_vision=True)

    clicks: list[tuple[float, float]] = []
    keys: list[str] = []
    monkeypatch.setattr(
        mod.ModalHandler, "_click_norm", lambda _s, _h, x, y: clicks.append((x, y)) or True
    )
    monkeypatch.setattr(
        mod.ModalHandler,
        "_query_modal_vision_sync",
        lambda *_a, **_k: pytest.fail("asked the model about the pause menu"),
    )
    monkeypatch.setattr(
        handler.input_controller,
        "tap_key",
        lambda key, **_k: keys.append(key),
    )
    monkeypatch.setattr(mod, "grab_rgb_image", lambda _h: menu)
    monkeypatch.setattr(
        mod,
        "grab_and_classify",
        lambda _h: UiClassification(
            mode=CampaignUiMode.CAMPAIGN_MAP, confidence=0.7, detail="cleared"
        ),
    )

    handler.handle(
        1, UiClassification(mode=CampaignUiMode.MODAL, confidence=0.9, detail="panel_over_centre")
    )

    assert keys == ["escape"], f"expected a single Escape, got {keys}"
    assert clicks == [], f"clicked inside the pause menu at {clicks}"
