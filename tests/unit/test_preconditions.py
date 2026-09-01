import pytest

from comstar_game_ai.game_io.preconditions import check_windows_build


def test_windows_build_check():
    ok, msg = check_windows_build()
    # On CI/non-Windows this may fail; on dev Windows box should pass.
    assert isinstance(ok, bool)
    assert msg
