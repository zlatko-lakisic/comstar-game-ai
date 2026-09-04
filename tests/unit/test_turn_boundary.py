from comstar_game_ai.game_io.logs.turn_boundary import new_turn_boundary_since, turn_boundary_in_tail


def test_turn_boundary_in_tail_end_sav():
    tail = 'Campaign saved: "./saves/Turn 5 End.sav" for year -268'
    assert turn_boundary_in_tail(tail)


def test_turn_boundary_in_tail_new_round():
    tail = "************new round start turn(romans_julii)************"
    assert turn_boundary_in_tail(tail)


def test_turn_boundary_in_tail_negative():
    assert not turn_boundary_in_tail("Music manager being set to state stratmap_winter")


def test_new_turn_boundary_ignores_historical_tail(tmp_path, monkeypatch):
    log = tmp_path / "message_log.txt"
    historical = "************new round start turn(romans_julii)************\n"
    log.write_text(historical, encoding="utf-8")
    before = log.stat().st_size

    monkeypatch.setattr(
        "comstar_game_ai.game_io.logs.turn_boundary.default_message_log_path",
        lambda: log,
    )
    assert not new_turn_boundary_since(before)

    with log.open("a", encoding="utf-8") as fh:
        fh.write("Campaign saved: Turn 4 End\n")
    assert new_turn_boundary_since(before)
