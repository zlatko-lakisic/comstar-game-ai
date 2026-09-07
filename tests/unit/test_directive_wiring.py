"""Whether AO's answer can reach the turn at all.

`campaign.directive.enabled` was a setting nothing read. The campaign loop always
built its driver without a directive store, so the driver's directive path was
unreachable and Process B could deliberate all it liked while the game played its
hardcoded policy.
"""

from __future__ import annotations

import pytest

from comstar_game_ai.game_io.runtime import GameIoRuntime


@pytest.fixture
def runtime():
    return GameIoRuntime()


def _config(*, enabled: bool, path: str | None = None, max_age: float | None = 900.0):
    directive: dict[str, object] = {"enabled": enabled}
    if path is not None:
        directive["path"] = path
    if max_age is not None:
        directive["max_age_s"] = max_age
    return {"campaign": {"directive": directive}}


def test_the_driver_gets_no_store_when_directives_are_off(runtime, monkeypatch):
    """Off means the hardcoded policy, not a loop that holds every turn."""
    monkeypatch.setattr(
        "comstar_game_ai.game_io.runtime.load_config", lambda: _config(enabled=False)
    )

    assert runtime._directive_wiring() == {}


def test_turning_it_on_hands_the_driver_the_store(runtime, monkeypatch):
    monkeypatch.setattr(
        "comstar_game_ai.game_io.runtime.load_config", lambda: _config(enabled=True)
    )

    wiring = runtime._directive_wiring()

    assert wiring["directive_store"] is runtime.directive_store
    assert wiring["directive_max_age_s"] == 900.0


def test_a_configured_path_wins_over_the_default(runtime, monkeypatch, tmp_path):
    elsewhere = tmp_path / "directive.json"
    monkeypatch.setattr(
        "comstar_game_ai.game_io.runtime.load_config",
        lambda: _config(enabled=True, path=str(elsewhere)),
    )

    wiring = runtime._directive_wiring()

    assert wiring["directive_store"].path == elsewhere


def test_the_wiring_is_what_the_driver_accepts(runtime, monkeypatch):
    """The point of the whole thing: these have to be real driver arguments.

    Passing them as `**kwargs` means a rename would fail here rather than at the
    start of a twenty-turn run.
    """
    from comstar_game_ai.game_io.drivers.hardcoded_campaign import HardcodedCampaignDriver

    monkeypatch.setattr(
        "comstar_game_ai.game_io.runtime.load_config", lambda: _config(enabled=True)
    )

    driver = HardcodedCampaignDriver(
        player_faction="julii", seed_from_setup=False, **runtime._directive_wiring()
    )

    assert driver.directive_store is runtime.directive_store
