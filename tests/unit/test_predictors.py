from pathlib import Path

from comstar_game_ai.agent.predictors.auto_resolve import estimate_auto_resolve
from comstar_game_ai.agent.predictors.economy import estimate_income
from comstar_game_ai.agent.predictors.game_data import load_unit_db, unit_strength
from comstar_game_ai.agent.predictors.log import PredictionLog
from comstar_game_ai.agent.predictors.melee import estimate_melee
from comstar_game_ai.agent.predictors.morale import estimate_morale
from comstar_game_ai.agent.predictors.movement import estimate_reach
from comstar_game_ai.agent.predictors.siege import estimate_siege_duration
from comstar_game_ai.shared.config import repo_root


FIXTURE = repo_root() / "tests" / "fixtures" / "edu" / "sample_units.json"


def test_load_unit_db():
    db = load_unit_db(FIXTURE)
    assert "roman_hastati" in db
    assert db["roman_principes"].attack == 8
    assert unit_strength(db["roman_hastati"], 60) > 0


def test_melee_estimate_favors_stronger():
    db = load_unit_db(FIXTURE)
    est = estimate_melee(
        db["roman_principes"],
        db["barbarian_warband"],
        attacker_men=80,
        defender_men=80,
        charging=True,
    )
    assert est.attacker_wins
    assert est.defender_casualty_rate > est.attacker_casualty_rate


def test_morale_rout_on_heavy_losses():
    est = estimate_morale(
        current_morale=20,
        current_fatigue=40,
        casualties_fraction=0.5,
        flank_exposed=True,
    )
    assert est.will_rout


def test_auto_resolve_ratio():
    db = load_unit_db(FIXTURE)
    own = [(db["roman_principes"], 120), (db["roman_equites"], 60)]
    enemy = [(db["barbarian_warband"], 80)]
    result = estimate_auto_resolve(own, enemy)
    assert result["strength_ratio"] > 1.0
    assert result["outcome"] in ("win", "decisive_win")


def test_campaign_stubs():
    siege = estimate_siege_duration(garrison_strength=500, attacker_strength=1200, wall_level=2)
    assert siege["turns_to_capture"] <= 8
    econ = estimate_income(settlements=5, avg_tax=400, upkeep=1000, turns=3)
    assert econ["projected_treasury_delta"] == 3000
    move = estimate_reach(movement_points=10, destination_distance=8)
    assert move["reachable"]


def test_prediction_log_pairs_outcome(tmp_path: Path):
    log_path = tmp_path / "predictions.jsonl"
    plog = PredictionLog(log_path)
    entry_id = plog.log_prediction("melee", {"attacker_wins": True}, context={"tick": 1})
    plog.record_outcome(entry_id, {"attacker_wins": True, "attacker_casualty_rate": 0.12})
    rows = plog.read_all()
    paired = [r for r in rows if r.get("observed") is not None]
    assert len(paired) == 1
    assert paired[0]["predicted"]["attacker_wins"] is True
