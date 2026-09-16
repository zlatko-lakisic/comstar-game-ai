"""March target label helper — no Rome required."""

from __future__ import annotations

from types import SimpleNamespace

from comstar_game_ai.game_io.drivers.hardcoded_campaign import _march_target_label


def test_march_target_label_prefers_field():
    order = SimpleNamespace(target_label="Segesta", command="march Flavius toward patavium")
    assert _march_target_label(order) == "Segesta"


def test_march_target_label_strips_set_prefix():
    order = SimpleNamespace(target_label="set_segesta", command="")
    assert _march_target_label(order) == "segesta"


def test_march_target_label_falls_back_to_toward_token():
    order = SimpleNamespace(
        target_label="",
        command="march Flavius Julius toward segesta",
    )
    assert _march_target_label(order) == "segesta"
