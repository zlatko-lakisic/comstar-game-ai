"""Tests for message_log campaign-map inference."""

from comstar_game_ai.game_io.logs.campaign_probe import (
    count_player_turn_starts,
    infer_campaign_map_from_message_log,
    is_campaign_session_ready,
    latest_julii_autosave_turn,
    latest_julii_load_turn,
    summarize_julii_turn_markers,
)
from comstar_game_ai.game_io.state_machine import GameState, GameStateDetector


def test_latest_julii_autosave_turn():
    text = 'Campaign saved: "./saves/save_Autosave   The House of Julii   Turn 5 Start.sav" for year -268'
    assert latest_julii_autosave_turn(text) == 5


def test_is_campaign_session_ready_from_load_line():
    text = (
        "Music manager being set to state stratmap_winter\n"
        'Attempting to load "./saves/save_Autosave   The House of Julii   Turn 4 End.sav"\n'
    )
    ready, turn = is_campaign_session_ready(text)
    assert ready
    assert turn == 4


def test_latest_julii_load_turn():
    text = (
        'Attempting to load "./saves/save_Autosave   The House of Julii   Turn 4 End.sav" '
        "however stored mods differ"
    )
    assert latest_julii_load_turn(text) == 4


def test_summarize_julii_turn_markers():
    text = (
        "************new round start turn(romans_julii)************\n"
        'Attempting to load "./saves/save_Autosave   The House of Julii   Turn 4 End.sav"\n'
        "Campaign saved: ./saves/save_Autosave   The House of Julii   Turn 5 Start.sav\n"
    )
    summary = summarize_julii_turn_markers(text)
    assert summary["round_starts"] == 1
    assert summary["autosave_turn"] == 5
    assert summary["load_turn"] == 4
    assert summary["known_turn"] == 5


def test_count_player_turn_starts():
    text = (
        "new round start turn(romans_brutii)\n"
        "************new round start turn(romans_julii)************\n"
        "************new round start turn(romans_julii)************\n"
    )
    assert count_player_turn_starts(text, player_faction="julii") == 2


def test_infer_campaign_map_from_stratmap_tail():
    text = (
        "Mods Enabled: 1\n"
        "Music manager being set to state frontend\n"
        "...\n"
        "************new round start turn(romans_julii)************\n"
        "Music manager being set to state stratmap_summer\n"
        "Campaign saved: Turn 3 Start.sav\n"
    )
    on_map, turn = infer_campaign_map_from_message_log(text, player_faction="julii")
    assert on_map
    assert turn == 3


def test_infer_not_campaign_on_frontend_only():
    text = "Music manager being set to state frontend\n"
    on_map, _ = infer_campaign_map_from_message_log(text)
    assert not on_map


def test_state_detector_infers_from_message_log():
    det = GameStateDetector()
    text = "Music manager being set to state stratmap_winter\n"
    changed = det.infer_from_message_log(text, player_faction="julii")
    assert changed == GameState.CAMPAIGN_MAP
    assert det.allows_campaign_orders()
