"""A report scroll has nothing to click, and does not answer Escape.

The battle report is the case that stalled a run. It states what happened — "CLOSE
DEFEAT", Quintus Julius with 21 men left of 200, against 388 Gauls — and its only
control is a lone tick centred beneath it. Every localizer hunts a coloured
accept/reject pair, so all of them found nothing; there was no close X; and the
scroll ignores Escape. The loop printed "no dismissible controls found" about four
hundred times while the campaign sat on turn 29.

Enter is the panel's default action, which on a report is that tick. The ordering
is the safety property worth pinning: on a panel that offers a choice, the default
may be the choice we do not want.
"""

from __future__ import annotations

import pytest

from comstar_game_ai.game_io.campaign.modal import ModalHandler
from comstar_game_ai.game_io.campaign.ui_mode import CampaignUiMode, UiClassification


class FakeController:
    def __init__(self) -> None:
        self.keys: list[str] = []
        self.clicks: list[tuple[float, float]] = []

    def tap_key(self, key: str, **_kw) -> bool:
        self.keys.append(key)
        return True


@pytest.fixture
def controller():
    return FakeController()


def _modal(detail: str = "left_overlay_panel") -> UiClassification:
    return UiClassification(mode=CampaignUiMode.MODAL, confidence=0.86, detail=detail)


def _map() -> UiClassification:
    return UiClassification(
        mode=CampaignUiMode.CAMPAIGN_MAP, confidence=0.70, detail="high_center_variance"
    )


def test_enter_acknowledges_a_report(controller, monkeypatch):
    handler = ModalHandler(input_controller=controller, settle_s=0.0)
    monkeypatch.setattr(
        "comstar_game_ai.game_io.campaign.modal.grab_and_classify", lambda _h: _map()
    )

    result = handler._acknowledge_report(1, _modal())

    assert controller.keys == ["enter"]
    assert result.mode == CampaignUiMode.CAMPAIGN_MAP


def test_a_scroll_that_ignores_enter_is_reported_not_hidden(controller, monkeypatch):
    """Giving up has to stay visible, or the next stall has no evidence."""
    handler = ModalHandler(input_controller=controller, settle_s=0.0)
    monkeypatch.setattr(
        "comstar_game_ai.game_io.campaign.modal.grab_and_classify", lambda _h: _modal()
    )

    result = handler._acknowledge_report(1, _modal())

    assert result.mode == CampaignUiMode.MODAL


def test_escape_is_tried_before_enter(controller, monkeypatch):
    """Escape is harmless; Enter commits the default. Order is the safety property.

    On a panel offering a choice the default may be the choice we do not want, so
    Enter must only run once the accept/reject search, the close X and Escape have
    all found nothing.
    """
    handler = ModalHandler(input_controller=controller, settle_s=0.0)
    seen: list[UiClassification] = [_modal(), _map()]
    monkeypatch.setattr(
        "comstar_game_ai.game_io.campaign.modal.grab_and_classify",
        lambda _h: seen.pop(0) if seen else _map(),
    )
    monkeypatch.setattr(
        "comstar_game_ai.game_io.campaign.modal.grab_rgb_image", lambda _h: object()
    )
    monkeypatch.setattr(
        "comstar_game_ai.game_io.campaign.modal.panel_bounds", lambda _i: (280, 1642, 13)
    )
    monkeypatch.setattr(
        "comstar_game_ai.game_io.campaign.modal.blocking_ui_present", lambda _i: True
    )
    monkeypatch.setattr(
        "comstar_game_ai.game_io.campaign.modal.left_overlay_parchment_ratio", lambda _i: 0.30
    )
    monkeypatch.setattr(
        "comstar_game_ai.game_io.campaign.modal.localize_panel_close_x", lambda _i: None
    )

    handler._close_panel(1, object(), 0.30)

    assert controller.keys[0] == "escape", f"Enter came first: {controller.keys}"
    assert "enter" in controller.keys, f"never acknowledged the report: {controller.keys}"
    assert controller.keys.index("escape") < controller.keys.index("enter")
