import pytest

from comstar_game_ai.game_io.capture.factory import configured_capture_backend
from comstar_game_ai.game_io.preconditions import check_preconditions, check_windows_build


def test_windows_build_check():
    ok, msg = check_windows_build()
    # On CI/non-Windows this may fail; on dev Windows box should pass.
    assert isinstance(ok, bool)
    assert msg


def test_configured_backend_defaults_to_wgc():
    assert configured_capture_backend({"capture": {}}) == "wgc"
    assert configured_capture_backend({"capture": {"backend": "WGC"}}) == "wgc"


def test_mss_backend_fails_preconditions(monkeypatch):
    monkeypatch.setattr(
        "comstar_game_ai.game_io.preconditions.load_config",
        lambda: {"capture": {"backend": "mss"}, "game": {}},
    )
    monkeypatch.setattr(
        "comstar_game_ai.game_io.preconditions.find_game_window",
        lambda _subs: None,
    )
    result = check_preconditions(require_game=False)
    assert not result.ok
    assert any("mss" in f for f in result.failures)
