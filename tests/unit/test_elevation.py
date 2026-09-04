"""Unit tests for elevation matching / UAC relaunch helpers."""

from __future__ import annotations

import sys

from comstar_game_ai.game_io.elevation import (
    ELEVATION_MARKER,
    TRAIL_FLAG,
    needs_elevation_for_pid,
    strip_elevation_marker,
    tee_output,
    trail_path_from_argv,
)


def test_strip_elevation_marker():
    assert strip_elevation_marker(["--rome", ELEVATION_MARKER, "--seconds", "5"]) == [
        "--rome",
        "--seconds",
        "5",
    ]


def test_strip_elevation_marker_drops_the_trail_flag():
    """Both relaunch flags are internal; the script's own argparse must never see them."""
    args = ["--seconds", "5", ELEVATION_MARKER, f"{TRAIL_FLAG}=D:/runtime/live.log"]
    assert strip_elevation_marker(args) == ["--seconds", "5"]


def test_trail_path_from_argv():
    assert trail_path_from_argv([f"{TRAIL_FLAG}=D:/runtime/live.log"]) == "D:/runtime/live.log"
    assert trail_path_from_argv(["--seconds", "5"]) is None


def test_tee_output_writes_the_console_trail_to_the_file(tmp_path, capsys):
    """An elevated run's only trail used to be an unreadable console window."""
    trail = tmp_path / "nested" / "live.log"
    original_out, original_err = sys.stdout, sys.stderr
    try:
        assert tee_output(str(trail)) == str(trail)
        print("ATTEMPT 1/20 game_turn=1")
    finally:
        sys.stdout, sys.stderr = original_out, original_err
    assert "ATTEMPT 1/20 game_turn=1" in trail.read_text(encoding="utf-8")
    assert "ATTEMPT 1/20 game_turn=1" in capsys.readouterr().out


def test_needs_elevation_when_game_elevated(monkeypatch):
    monkeypatch.setattr("comstar_game_ai.game_io.elevation.is_current_elevated", lambda: False)
    monkeypatch.setattr("comstar_game_ai.game_io.elevation.process_is_elevated", lambda _pid: True)
    assert needs_elevation_for_pid(1) is True


def test_needs_elevation_when_token_unreadable(monkeypatch):
    monkeypatch.setattr("comstar_game_ai.game_io.elevation.is_current_elevated", lambda: False)
    monkeypatch.setattr("comstar_game_ai.game_io.elevation.process_is_elevated", lambda _pid: None)
    assert needs_elevation_for_pid(1) is True


def test_no_elevation_when_both_non_admin(monkeypatch):
    monkeypatch.setattr("comstar_game_ai.game_io.elevation.is_current_elevated", lambda: False)
    monkeypatch.setattr("comstar_game_ai.game_io.elevation.process_is_elevated", lambda _pid: False)
    assert needs_elevation_for_pid(1) is False


def test_no_elevation_when_already_admin(monkeypatch):
    monkeypatch.setattr("comstar_game_ai.game_io.elevation.is_current_elevated", lambda: True)
    monkeypatch.setattr("comstar_game_ai.game_io.elevation.process_is_elevated", lambda _pid: True)
    assert needs_elevation_for_pid(1) is False
