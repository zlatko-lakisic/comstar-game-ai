"""A vision call must report in while it blocks.

The safety deadman allows ten seconds. A modal classification on a shared GPU took
far longer and nothing pet the deadman while it waited, so the watchdog fired
mid-turn, killed input, and left the loop clicking at a game it no longer
controlled. The vision answer then arrived and was correct, which is what made it
look like a vision problem rather than a stalled pet.
"""

from __future__ import annotations

import time

from comstar_game_ai.game_io.campaign.modal import ModalHandler


def test_a_slow_vision_call_keeps_petting_the_deadman(monkeypatch):
    pets: list[float] = []
    handler = ModalHandler(model_timeout_s=8.0, on_heartbeat=lambda: pets.append(time.time()))

    async def slow(*_args, **_kwargs):
        import asyncio

        await asyncio.sleep(5.0)
        return None

    monkeypatch.setattr(
        "comstar_game_ai.game_io.campaign.modal._query_modal_vision_async", slow
    )

    handler._query_modal_vision_sync(object(), request_id="t", turn=1, ui_mode="modal")

    assert len(pets) >= 3, f"deadman would have fired: only {len(pets)} pets in 5s"
    gaps = [b - a for a, b in zip(pets, pets[1:], strict=False)]
    assert all(gap < 10.0 for gap in gaps), f"a gap outlasted the deadman: {gaps}"


def test_giving_up_on_a_call_does_not_block_on_it(monkeypatch):
    """Where the deadman actually fired: on the way out of the wait, not during it.

    A `with ThreadPoolExecutor(...)` block calls `shutdown(wait=True)` when left, so
    abandoning an overrunning request meant blocking on that same request outside
    the loop doing the petting. The whole point of the timeout is to stop waiting.
    """
    handler = ModalHandler(model_timeout_s=0.5, on_heartbeat=lambda: None)

    async def never(*_args, **_kwargs):
        import asyncio

        await asyncio.sleep(30.0)
        return None

    monkeypatch.setattr(
        "comstar_game_ai.game_io.campaign.modal._query_modal_vision_async", never
    )

    began = time.time()
    result = handler._query_modal_vision_sync(object(), request_id="t", turn=1, ui_mode="m")
    took = time.time() - began

    assert result is None
    assert took < 15.0, f"blocked on the call it gave up on: {took:.1f}s"


def test_no_heartbeat_configured_is_not_an_error(monkeypatch):
    """Dry tests and one-off scripts construct this without a safety controller."""
    handler = ModalHandler(model_timeout_s=1.0)

    async def nothing(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        "comstar_game_ai.game_io.campaign.modal._query_modal_vision_async", nothing
    )

    assert handler._query_modal_vision_sync(object(), request_id="t", turn=1, ui_mode="m") is None


def test_a_failing_heartbeat_does_not_take_down_the_turn(monkeypatch):
    def angry() -> None:
        raise RuntimeError("watchdog is gone")

    handler = ModalHandler(model_timeout_s=1.0, on_heartbeat=angry)

    async def nothing(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        "comstar_game_ai.game_io.campaign.modal._query_modal_vision_async", nothing
    )

    assert handler._query_modal_vision_sync(object(), request_id="t", turn=1, ui_mode="m") is None


def test_resolving_a_battle_reports_in_while_it_watches(monkeypatch):
    """The last unpetted loop, and it ended the 20-turn run on turn 29.

    Auto-resolve clicks once and then watches the panel for up to two minutes,
    sleeping in two-second steps. Nothing pet the deadman, so the watchdog released
    input mid-battle — after which no click could clear anything, and the loop spent
    the rest of its timeout watching a panel it could no longer touch, which is why
    this surfaced as "battle panel did not clear" rather than as a watchdog problem.
    """
    from comstar_game_ai.game_io.campaign import combat

    # A battle that is up and stays up, so the whole wait runs.
    monkeypatch.setattr(combat, "battle_deployment_present", lambda _frame: True)
    monkeypatch.setattr(combat.CombatDirector, "_click_norm", lambda *_a, **_k: True)

    pets: list[int] = []
    director = combat.CombatDirector(
        hwnd=1,
        capture=lambda: object(),
        sleep=lambda _s: time.sleep(0.02),
        battle_timeout_s=1.0,
        on_heartbeat=lambda: pets.append(1),
    )

    assert director.resolve_battle() is False, "the panel never cleared, by construction"
    assert len(pets) >= 5, f"the watchdog heard nothing for a full battle wait: {len(pets)}"


def test_the_configured_timeout_is_not_longer_than_a_turn():
    """180 seconds bought nothing and cost more than the turns around it."""
    from comstar_game_ai.shared.config import load_config

    modal = (load_config().get("campaign") or {}).get("modal") or {}

    assert float(modal.get("model_timeout_s", 30)) <= 30.0
