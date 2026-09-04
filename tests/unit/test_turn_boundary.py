import comstar_game_ai.game_io.logs.turn_boundary as turn_boundary
from comstar_game_ai.game_io.logs.turn_boundary import latest_turn_end, wait_for_turn_end

AUTOSAVE = (
    'Campaign saved: "./saves/save_Autosave   The House of Julii   Turn {n} End.sav"'
    " for year -262, season winter\n"
)
ROUND_START = "************new round start turn(romans_julii)************\n"


def _log(tmp_path, monkeypatch, text):
    log = tmp_path / "message_log.txt"
    log.write_text(text, encoding="utf-8")
    monkeypatch.setattr(turn_boundary, "default_message_log_path", lambda: log)
    return log


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
