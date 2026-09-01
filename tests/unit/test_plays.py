from comstar_game_ai.agent.reactive.plays import PlaysExecutor, PLAYBOOK


def test_hammer_anvil_runs_all_steps():
    steps = []

    def record(step):
        steps.append(step.action)
        return True

    ex = PlaysExecutor(on_step=record)
    assert ex.run("hammer_anvil")
    assert steps == ["hold_position", "flank_charge"]


def test_unknown_play_fails():
    ex = PlaysExecutor()
    assert not ex.run("nonexistent")


def test_playbook_has_adopted_plays():
    assert "hammer_anvil" in PLAYBOOK
    assert "feigned_retreat" in PLAYBOOK
