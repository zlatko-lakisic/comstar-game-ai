"""Unit tests for elevation matching / UAC relaunch helpers."""

from __future__ import annotations

from comstar_game_ai.game_io.elevation import (
    ELEVATION_MARKER,
    needs_elevation_for_pid,
    strip_elevation_marker,
)


def test_strip_elevation_marker():
    assert strip_elevation_marker(["--rome", ELEVATION_MARKER, "--seconds", "5"]) == [
        "--rome",
        "--seconds",
        "5",
    ]


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
