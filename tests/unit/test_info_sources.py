"""Tests for the per-game campaign information catalog."""

from __future__ import annotations

from comstar_game_ai.game_io.campaign.info_sources import BY_ID, SOURCES
from comstar_game_ai.game_io.campaign.ui_atlas import BY_ID as PANELS


def test_ids_are_unique():
    assert len(BY_ID) == len(SOURCES)
    assert SOURCES


def test_every_source_names_a_question_and_a_read():
    for source in SOURCES:
        assert source.question.endswith("?")
        assert source.surface
        assert source.how
        assert source.reads


def test_authoritative_surfaces_are_not_the_traps():
    """The catalog exists to stop these substitutions."""
    economy = BY_ID["settlement_economy"]
    assert economy.surface == "lists_scroll"
    assert "Ctrl+5" in economy.how
    assert "not population" in economy.trap.lower()
    owner = BY_ID["settlement_owner"]
    assert "hover" in owner.how.lower()
    assert "colour" in owner.trap.lower()
    treasury = BY_ID["treasury"]
    assert "HUD" in treasury.how
    assert "Boundless" in treasury.trap


def test_senate_mission_is_not_the_senate_window():
    source = BY_ID["senate_mission"]
    assert source.surface == "event_log.missions"
    assert "Ctrl+2" in source.trap
    assert "senate_window" in PANELS


def test_lists_locate_warns_about_the_capital_button():
    assert "capital" in BY_ID["find_owned_settlement"].trap.lower()


def test_agent_reads_do_not_confuse_the_three_surfaces():
    identity = BY_ID["agent_identity"]
    traits = BY_ID["agent_traits"]
    roster = BY_ID["agent_roster"]
    assert identity.surface == "agent_selection_hud"
    assert "followers" in identity.trap.lower()
    assert traits.surface == "character_scroll"
    assert "wiki" in traits.trap.lower()
    assert roster.surface == "lists_scroll"
    assert "assign" in roster.trap.lower()
    distance = BY_ID["agent_target_distance"]
    assert "turn glyph" in distance.how.lower() or "turn glyph" in distance.reads.lower()
    assert "eporedorix" in distance.trap.lower()
    assert "senaculus" in distance.trap.lower()


def test_build_and_unlock_reads_do_not_click_to_spend():
    build = BY_ID["build_options"]
    recruit = BY_ID["recruit_options"]
    unlock = BY_ID["building_unlock_line"]
    assert "hover" in build.how.lower()
    assert "spend" in build.trap.lower()
    assert "hover" in recruit.how.lower()
    assert "spend" in recruit.trap.lower()
    assert unlock.surface == "building_browser"
    assert "accept" in unlock.trap.lower()
    assert "building_browser" in PANELS
    roster = BY_ID["army_roster"]
    assert roster.surface == "lists_scroll"
    assert "capital" in roster.trap.lower()
    order = BY_ID["map_order"]
    assert "glyph" in order.how.lower()
    assert "left-click" in order.how.lower()
    assert "right click" in order.trap.lower()


def test_event_log_reads_use_the_games_own_empty_states():
    assert "NO ALERTS" in BY_ID["pending_alerts"].reads
    assert "NO NEWS" in BY_ID["pending_news"].reads
    assert "NO REPORTS" in BY_ID["pending_reports"].reads
