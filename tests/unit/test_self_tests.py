import pytest

from comstar_game_ai.game_io.self_tests import run_self_tests


@pytest.mark.requires_game
def test_self_tests_without_game():
    result = run_self_tests(require_game=False)
    # Without Rome running, preconditions may pass but game tests skip gracefully.
    assert "preconditions" in result.tests
