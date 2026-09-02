import pytest

from comstar_game_ai.game_io.fair_play import CommandClass, FairPlayGate


@pytest.fixture
def gate():
    return FairPlayGate()


def test_allowed_move(gate):
    assert gate.allow("move_character Caesar 10,20")
    assert gate.classify("move_character x") == CommandClass.ALLOWED


def test_never_add_money(gate):
    assert not gate.allow("add_money 5000")
    assert gate.classify("add_money") == CommandClass.NEVER


def test_evaluation_taints(gate):
    assert gate.allow("toggle_fow")
    assert gate.evaluation_tainted


def test_unknown_fail_closed(gate):
    assert not gate.allow("totally_unknown_cheat")
    assert gate.classify("totally_unknown_cheat") == CommandClass.NEVER
