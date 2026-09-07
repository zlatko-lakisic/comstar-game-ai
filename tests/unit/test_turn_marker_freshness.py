"""Turn detection has to survive the numbering starting over.

A run started beside a finished campaign read the leftover `Turn 20 Start.sav` as
its baseline and waited for turn 21, while the game sat on turn 1 of a new
campaign at 270 BC. Nothing it waited for could ever happen, so every turn spent
its full 180-second timeout and the run reported `turns_advanced: 0` — which
reads exactly like a game ignoring End Turn.
"""

from __future__ import annotations

import time

import pytest

from comstar_game_ai.game_io.drivers.hardcoded_campaign import HardcodedCampaignDriver
from comstar_game_ai.game_io.logs import turn_boundary


@pytest.fixture
def saves(tmp_path, monkeypatch):
    folder = tmp_path / "saves"
    folder.mkdir()
    monkeypatch.setattr(turn_boundary, "default_saves_dir", lambda: folder)
    return folder


def write_save(folder, name: str, *, mtime: float) -> None:
    path = folder / name
    path.write_text("x", encoding="utf-8")
    import os

    os.utime(path, (mtime, mtime))


def test_the_newest_marker_is_the_newest_file_not_the_highest_turn(saves):
    old = time.time() - 3600
    write_save(saves, "save_Autosave   The House of Julii   Turn 20 Start.sav", mtime=old)
    write_save(saves, "save_Autosave   The House of Julii   Turn 2 Start.sav", mtime=time.time())

    marker = turn_boundary.newest_turn_start_marker()

    assert marker is not None
    assert marker[0] == 2, "the abandoned campaign's turn 20 is not where we are"


def test_no_saves_means_no_marker(saves):
    assert turn_boundary.newest_turn_start_marker() is None


@pytest.fixture
def driver(monkeypatch):
    d = HardcodedCampaignDriver(player_faction="julii", seed_from_setup=False)
    monkeypatch.setattr(d, "poll_observation", lambda: 0)
    monkeypatch.setattr(d, "_refresh_turn_from_message_log", lambda: None)
    return d


def test_a_fresh_campaign_beside_a_finished_one_still_advances(driver, saves, monkeypatch):
    """The bug, as a test: turn 1 of a new campaign under a leftover turn 20.

    Every number the driver can read says 20, and the new turn is numbered 2. The
    only thing that distinguishes progress is that Rome wrote the file just now.
    """
    write_save(
        saves,
        "save_Autosave   The House of Julii   Turn 20 Start.sav",
        mtime=time.time() - 3600,
    )
    # Whatever the stale logs claim the turn is, they claim it throughout.
    monkeypatch.setattr(driver, "_known_game_turn", lambda: 20)

    def hand_the_turn_back() -> None:
        time.sleep(0.4)
        write_save(
            saves,
            "save_Autosave   The House of Julii   Turn 2 Start.sav",
            mtime=time.time(),
        )

    import threading

    threading.Thread(target=hand_the_turn_back, daemon=True).start()

    assert driver.wait_for_turn_event(timeout_s=5.0) is True


def test_a_real_ending_is_not_scored_as_a_miss(saves):
    """Why a miss is dangerous, not merely wrong.

    `end_turn_campaign` reads a miss as "that actuation did nothing" and tries the
    next method. Against a leftover `Turn 19 End.sav`, a new campaign ending turn 1
    scored as a miss every time, so it pressed End Turn again — and ended turns 1
    and 2 in one call while reporting it had ended none.
    """
    old = time.time() - 3600
    write_save(saves, "save_Autosave   The House of Julii   Turn 19 End.sav", mtime=old)
    since = turn_boundary.newest_turn_end_marker()[1]

    write_save(
        saves, "save_Autosave   The House of Julii   Turn 1 End.sav", mtime=time.time()
    )

    assert turn_boundary.wait_for_turn_end(19, since=since, timeout_s=1.0) == 1


def test_nothing_new_is_still_a_miss(saves):
    """The check has to stay falsifiable: no new save, no boundary."""
    old = time.time() - 3600
    write_save(saves, "save_Autosave   The House of Julii   Turn 19 End.sav", mtime=old)
    since = turn_boundary.newest_turn_end_marker()[1]

    assert turn_boundary.wait_for_turn_end(19, since=since, timeout_s=0.5) is None


def test_a_turn_handed_back_while_end_turn_confirmed_still_counts(driver, saves, monkeypatch):
    """The fast-turn case, which the first version of this fix lost.

    Ending the turn polls the saves folder for up to ten seconds to confirm its own
    keypress, so a quick AI round writes `Turn N Start.sav` before the wait begins.
    Reading the baseline at the top of the wait therefore asked for the turn *after*
    the one we already had, and the cycle sat out its full 180-second timeout.
    """
    monkeypatch.setattr(driver, "_known_game_turn", lambda: 20)
    pressed_at = time.time()
    # Rome got there first: the handback is already on disk.
    write_save(
        saves,
        "save_Autosave   The House of Julii   Turn 3 Start.sav",
        mtime=pressed_at + 0.1,
    )

    assert driver.wait_for_turn_event(timeout_s=2.0, since=pressed_at - 1.0) is True


def test_a_turn_that_never_comes_back_still_times_out(driver, saves, monkeypatch):
    """The wait must not become unfalsifiable in the course of being fixed."""
    write_save(
        saves,
        "save_Autosave   The House of Julii   Turn 20 Start.sav",
        mtime=time.time() - 3600,
    )
    monkeypatch.setattr(driver, "_known_game_turn", lambda: 20)

    assert driver.wait_for_turn_event(timeout_s=1.0) is False
