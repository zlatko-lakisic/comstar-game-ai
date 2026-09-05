"""Takeover is offered only in a playable state — without repeating phase 2's mistake.

Phase 2 shipped a readiness gate that demanded positive proof the game was
playable, and it refused to start on a live campaign because dim winter maps and
open sea classify as unknown. This gate refuses only on confident evidence the
screen is *not* playable.
"""

from __future__ import annotations

import pytest

from comstar_game_ai.game_io import runtime as runtime_module
from comstar_game_ai.game_io.campaign.ui_mode import CampaignUiMode, UiClassification
from comstar_game_ai.game_io.runtime import GameIoRuntime
from comstar_game_ai.game_io.safety import ControlMode


@pytest.fixture
def host(monkeypatch):
    published: list[tuple] = []
    host = GameIoRuntime(require_game=False)
    monkeypatch.setattr(
        host.publisher, "publish", lambda kind, payload=None: published.append((kind, payload))
    )
    host._game_hwnd = 0x4242
    host.published = published  # type: ignore[attr-defined]
    return host


def _classifies_as(monkeypatch, mode, confidence: float, detail: str = "test"):
    monkeypatch.setattr(
        runtime_module,
        "grab_and_classify",
        lambda _hwnd: UiClassification(mode=mode, confidence=confidence, detail=detail),
    )


def test_takeover_is_refused_on_a_confident_pause_screen(host, monkeypatch):
    _classifies_as(monkeypatch, CampaignUiMode.PAUSE, 0.9, "dark_low_variance")
    assert host.refuse_takeover_reason() is not None
    host._on_takeover()
    assert host.safety.mode is ControlMode.IDLE


def test_a_refusal_is_reported_to_the_overlay(host, monkeypatch):
    _classifies_as(monkeypatch, CampaignUiMode.PAUSE, 0.9)
    host._on_takeover()
    assert host.published, "the operator was never told why nothing happened"  # type: ignore[attr-defined]


def test_takeover_proceeds_on_the_campaign_map(host, monkeypatch):
    _classifies_as(monkeypatch, CampaignUiMode.CAMPAIGN_MAP, 0.9)
    assert host.refuse_takeover_reason() is None
    host._on_takeover()
    assert host.safety.mode is ControlMode.AGENT


@pytest.mark.parametrize(
    "mode",
    [CampaignUiMode.UNKNOWN, CampaignUiMode.MODAL, CampaignUiMode.PRE_BATTLE],
)
def test_an_inconclusive_screen_does_not_block_takeover(host, monkeypatch, mode):
    """The phase 2 lesson: unknown is not proof of anything, least of all a menu."""
    _classifies_as(monkeypatch, mode, 0.0)
    assert host.refuse_takeover_reason() is None


def test_a_low_confidence_pause_reading_does_not_block_takeover(host, monkeypatch):
    """A dim winter map reads faintly like a pause screen; it is still playable."""
    _classifies_as(monkeypatch, CampaignUiMode.PAUSE, 0.3)
    assert host.refuse_takeover_reason() is None


def test_a_failing_classifier_does_not_block_takeover(host, monkeypatch):
    def explode(_hwnd):
        raise RuntimeError("capture died")

    monkeypatch.setattr(runtime_module, "grab_and_classify", explode)
    assert host.refuse_takeover_reason() is None


def test_no_game_window_means_no_gate(monkeypatch):
    host = GameIoRuntime(require_game=False)
    assert host._game_hwnd is None
    assert host.refuse_takeover_reason() is None


def test_the_gate_never_blocks_the_kill_switch(host, monkeypatch):
    """Whatever is on screen, kill must work. It is not gated on anything."""
    _classifies_as(monkeypatch, CampaignUiMode.PAUSE, 1.0)
    host.safety.mode = ControlMode.AGENT
    host._on_kill()
    assert host.safety.mode is ControlMode.KILLED


def test_handback_is_not_gated_either(host, monkeypatch):
    _classifies_as(monkeypatch, CampaignUiMode.PAUSE, 1.0)
    host.safety.takeover()
    host._on_handback()
    assert host.safety.mode is ControlMode.IDLE
