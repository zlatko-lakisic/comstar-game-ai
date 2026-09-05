import os
import time

import pytest

import comstar_game_ai.game_io.logs.turn_boundary as turn_boundary
from comstar_game_ai.game_io.logs.turn_boundary import (
    latest_turn_end,
    latest_turn_start,
    wait_for_turn_end,
)

AUTOSAVE = (
    'Campaign saved: "./saves/save_Autosave   The House of Julii   Turn {n} End.sav"'
    " for year -262, season winter\n"
)
ROUND_START = "************new round start turn(romans_julii)************\n"
SAVE_NAME = "save_Autosave   The House of Julii   Turn {n} End.sav"


@pytest.fixture(autouse=True)
def _no_real_saves(tmp_path, monkeypatch):
    """Point the saves lookup at an empty folder so tests never read the real game."""
    empty = tmp_path / "saves-empty"
    empty.mkdir()
    monkeypatch.setattr(turn_boundary, "default_saves_dir", lambda: empty)


def _log(tmp_path, monkeypatch, text):
    log = tmp_path / "message_log.txt"
    log.write_text(text, encoding="utf-8")
    monkeypatch.setattr(turn_boundary, "default_message_log_path", lambda: log)
    return log


def _saves(tmp_path, monkeypatch, turns_with_age):
    """Create `Turn N End.sav` files, `turns_with_age` mapping turn -> seconds old."""
    saves = tmp_path / "saves"
    saves.mkdir(exist_ok=True)
    now = time.time()
    for turn, age_s in turns_with_age.items():
        path = saves / SAVE_NAME.format(n=turn)
        path.write_bytes(b"savegame")
        stamp = now - age_s
        os.utime(path, (stamp, stamp))
    monkeypatch.setattr(turn_boundary, "default_saves_dir", lambda: saves)
    return saves


def test_latest_turn_end_reads_the_highest_autosaved_turn(tmp_path, monkeypatch):
    _log(tmp_path, monkeypatch, AUTOSAVE.format(n=8) + ROUND_START + AUTOSAVE.format(n=9))
    assert latest_turn_end() == 9


def test_latest_turn_end_is_none_without_an_autosave(tmp_path, monkeypatch):
    _log(tmp_path, monkeypatch, ROUND_START + "Music manager set to state stratmap_winter\n")
    assert latest_turn_end() is None


def test_latest_turn_end_is_none_without_a_log(tmp_path, monkeypatch):
    monkeypatch.setattr(turn_boundary, "default_message_log_path", lambda: tmp_path / "absent.txt")
    assert latest_turn_end() is None


def test_round_start_is_not_proof_a_turn_ended(tmp_path, monkeypatch):
    """The regression: a round-start line scored as a turn, double-counting turns.

    It is written when the AI round finishes, which usually falls inside the *next*
    attempt's wait window, so 20 attempts reported 19 successes over 10 real turns.
    """
    log = _log(tmp_path, monkeypatch, AUTOSAVE.format(n=9))
    with log.open("a", encoding="utf-8") as handle:
        handle.write(ROUND_START)
    assert wait_for_turn_end(9, timeout_s=0.0) is None


def test_reautosaving_the_same_turn_is_not_a_new_turn(tmp_path, monkeypatch):
    log = _log(tmp_path, monkeypatch, AUTOSAVE.format(n=9))
    with log.open("a", encoding="utf-8") as handle:
        handle.write(AUTOSAVE.format(n=9))
    assert wait_for_turn_end(9, timeout_s=0.0) is None


def test_a_later_turn_ends_the_wait(tmp_path, monkeypatch):
    log = _log(tmp_path, monkeypatch, AUTOSAVE.format(n=9))
    with log.open("a", encoding="utf-8") as handle:
        handle.write(ROUND_START + AUTOSAVE.format(n=10))
    assert wait_for_turn_end(9, timeout_s=0.0) == 10


def test_any_autosave_counts_when_none_has_been_seen(tmp_path, monkeypatch):
    """A fresh campaign has no autosave yet, so the first one is the first turn end."""
    log = _log(tmp_path, monkeypatch, ROUND_START)
    assert latest_turn_end() is None
    with log.open("a", encoding="utf-8") as handle:
        handle.write(AUTOSAVE.format(n=1))
    assert wait_for_turn_end(None, timeout_s=0.0) == 1


def test_autosave_files_prove_a_turn_ended_when_the_log_is_silent(tmp_path, monkeypatch):
    """The failure this exists for: Rome played a whole campaign writing no log at all.

    message_log.txt stayed frozen at its 77 startup lines while the campaign ran from
    turn 1 to turn 13, so every End Turn was scored a miss and fired up to three times.
    """
    _log(tmp_path, monkeypatch, "Loading unlocalised pack data/sounds/sfx\n")
    _saves(tmp_path, monkeypatch, {10: 120, 11: 60})
    assert latest_turn_end() == 11
    assert wait_for_turn_end(10, timeout_s=0.0) == 11


def test_the_newest_autosave_wins_over_a_higher_numbered_stale_one(tmp_path, monkeypatch):
    """An abandoned campaign at turn 69 must not mask a fresh one on turn 3."""
    _log(tmp_path, monkeypatch, "")
    _saves(tmp_path, monkeypatch, {69: 86_400 * 500, 3: 30})
    assert latest_turn_end() == 3


def test_the_higher_of_log_and_autosave_wins(tmp_path, monkeypatch):
    """Either record can lag, so neither is allowed to hold the count back."""
    _log(tmp_path, monkeypatch, AUTOSAVE.format(n=12))
    _saves(tmp_path, monkeypatch, {11: 30})
    assert latest_turn_end() == 12


def test_no_saves_folder_falls_back_to_the_log(tmp_path, monkeypatch):
    monkeypatch.setattr(turn_boundary, "default_saves_dir", lambda: tmp_path / "absent")
    _log(tmp_path, monkeypatch, AUTOSAVE.format(n=6))
    assert latest_turn_end() == 6


def test_start_autosaves_are_not_ended_turns(tmp_path, monkeypatch):
    """Rome writes `Turn N Start.sav` too; only the End save proves a turn ended."""
    _log(tmp_path, monkeypatch, "")
    saves = tmp_path / "saves"
    saves.mkdir()
    (saves / "save_Autosave   The House of Julii   Turn 14 Start.sav").write_bytes(b"s")
    monkeypatch.setattr(turn_boundary, "default_saves_dir", lambda: saves)
    assert latest_turn_end() is None


def test_turn_start_marks_control_coming_back(tmp_path, monkeypatch):
    """Ending a turn and getting the next one back are separate events.

    Observed 20s apart: `Turn 21 End.sav` at 8:22:52, `Turn 22 Start.sav` at 8:23:12.
    Treating the End save as the player's next turn issues orders mid-AI-round.
    """
    saves = tmp_path / "saves"
    saves.mkdir()
    now = time.time()
    for name, age_s in (
        (SAVE_NAME.format(n=21), 40),
        ("save_Autosave   The House of Julii   Turn 22 Start.sav", 20),
    ):
        path = saves / name
        path.write_bytes(b"savegame")
        os.utime(path, (now - age_s, now - age_s))
    monkeypatch.setattr(turn_boundary, "default_saves_dir", lambda: saves)

    assert latest_turn_end() == 21
    assert latest_turn_start() == 22


def test_turn_start_is_none_before_any_start_autosave(tmp_path, monkeypatch):
    _saves(tmp_path, monkeypatch, {5: 10})
    assert latest_turn_start() is None


def test_finds_the_turn_in_a_log_longer_than_the_tail_window(tmp_path, monkeypatch):
    """Campaign logs reach tens of megabytes; only the tail is read on each poll."""
    monkeypatch.setattr(turn_boundary, "_TAIL_BYTES", 512)
    padding = "Manius Burrus(romans_brutii:diplomat):MOVING_NORMAL:start(1,2):end(3,4)\n" * 200
    _log(tmp_path, monkeypatch, padding + AUTOSAVE.format(n=42))
    assert latest_turn_end() == 42


def test_falls_back_to_the_whole_log_when_the_tail_has_no_autosave(tmp_path, monkeypatch):
    monkeypatch.setattr(turn_boundary, "_TAIL_BYTES", 512)
    padding = "AI turn chatter that pushes the autosave out of the tail window\n" * 200
    _log(tmp_path, monkeypatch, AUTOSAVE.format(n=7) + padding)
    assert latest_turn_end() == 7
