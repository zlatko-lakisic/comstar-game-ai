"""Acceptance: belief store from fixture log lines."""

from comstar_game_ai.agent.belief.store import BeliefStore
from comstar_game_ai.game_io.logs.scripting_log import parse_key_value_line


def test_belief_from_script_lines():
    store = BeliefStore()
    line = parse_key_value_line("event=NewTurnStart turn=1 faction=julii")
    assert line["event"] == "NewTurnStart"
    store.history.append(line)
    assert len(store.history) == 1
