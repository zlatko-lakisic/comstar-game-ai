from pathlib import Path

from comstar_game_ai.game_io.battle.freeze_loop import FreezeCycleConfig, FreezeLoop
from comstar_game_ai.game_io.battle.orders import BattleOrder
from comstar_game_ai.game_io.battle.unit_positions import BattlePositions, UnitPosition


def test_freeze_cycle_toggles_and_issues_orders(tmp_path):
    console_cmds: list[str] = []
    issued: list[BattleOrder] = []

    def run_console(cmd: str) -> bool:
        console_cmds.append(cmd)
        if cmd.startswith("output_unit_positions"):
            path = Path(cmd.split(maxsplit=1)[1])
            path.write_text("0,0,0,10.0,20.0,90.0,20.0,40\n", encoding="utf-8")
        return True

    def decide(positions: BattlePositions, tick: int) -> list[BattleOrder]:
        assert tick == 0
        assert positions.total_men == 40
        return [BattleOrder("hold_position", unit_key=(0, 0, 0))]

    loop = FreezeLoop(
        run_console=run_console,
        positions_dir=tmp_path,
        decide=decide,
        config=FreezeCycleConfig(positions_filename="units.txt"),
        sleep=lambda _s: None,
    )

    assert loop.run_cycle()
    assert loop.tick == 1
    assert not loop.frozen
    assert console_cmds.count("toggle_game_update") == 2
    assert any(c.startswith("output_unit_positions") for c in console_cmds)
    assert loop._issuer.pending[0].action == "hold_position"


def test_freeze_loop_unfreezes_on_failure(tmp_path):
    toggles = {"count": 0}

    def run_console(cmd: str) -> bool:
        if cmd == "toggle_game_update":
            toggles["count"] += 1
        return True

    loop = FreezeLoop(
        run_console=run_console,
        positions_dir=tmp_path,
        decide=lambda _p, _t: [],
        sleep=lambda _s: None,
    )
    loop.run_cycle()
    assert toggles["count"] == 2


def test_run_until_stops_on_condition(tmp_path):
    (tmp_path / "comstar_unit_positions.txt").write_text(
        "0,0,0,0,0,0,20,10\n1,0,0,100,100,0,20,10\n",
        encoding="utf-8",
    )
    ticks: list[int] = []

    loop = FreezeLoop(
        run_console=lambda cmd: True,
        positions_dir=tmp_path,
        decide=lambda _p, t: (ticks.append(t) or [BattleOrder("hold_position")]),
        sleep=lambda _s: None,
    )

    def stop(tick: int, positions: BattlePositions) -> bool:
        return tick >= 2

    ran = loop.run_until(stop, max_ticks=10)
    assert ran == 2
    assert ticks == [0, 1]
