"""Tests for the long-term campaign learning corpus."""

from __future__ import annotations

from pathlib import Path

import yaml

from comstar_game_ai.agent.learning.campaign_learnings import (
    BY_ID,
    LEARNINGS,
    Valence,
    by_valence,
)


def test_ids_are_unique():
    assert len(BY_ID) == len(LEARNINGS)
    assert LEARNINGS


def test_every_learning_is_an_action_outcome_pair():
    for item in LEARNINGS:
        assert item.action
        assert item.outcome
        assert item.lesson
        assert item.evidence
        assert item.valence in Valence


def test_failures_are_kept_so_retrieval_is_not_a_highlight_reel():
    bad = by_valence(Valence.BAD)
    good = by_valence(Valence.GOOD)
    assert bad, "a corpus of only successes teaches superstition"
    assert good, "there must be something worth repeating"
    assert {item.valence for item in LEARNINGS} == set(Valence)


def test_escape_on_a_clear_map_is_recorded_as_bad():
    item = BY_ID["escape_on_clear_map_pauses"]
    assert item.valence is Valence.BAD
    assert "pause" in item.outcome.lower()


def test_selected_tab_toggle_is_mixed_not_a_mystery():
    item = BY_ID["selected_event_log_tab_toggles_shut"]
    assert item.valence is Valence.MIXED
    assert "collapsed" in item.outcome.lower()


def test_agent_dispatch_and_disband_stay_in_the_failure_list():
    assert BY_ID["agent_hub_confirm_dispatches"].valence is Valence.BAD
    assert BY_ID["disband_boot_is_live"].valence is Valence.BAD
    assert BY_ID["send_list_is_three_clicks"].valence is Valence.GOOD
    assert "confirm" in BY_ID["agent_hub_confirm_dispatches"].lesson.lower()
    eyeball = BY_ID["spy_on_nearest_gallic_character"]
    assert eyeball.valence is Valence.BAD
    assert "glyph" in eyeball.lesson.lower()
    assert BY_ID["send_list_turn_glyph_is_distance"].valence is Valence.GOOD
    assert BY_ID["building_browser_tree_disc_opens"].valence is Valence.GOOD
    assert "x" in BY_ID["building_browser_tree_disc_opens"].lesson.lower()
    order = BY_ID["map_order_waits_for_the_cursor_glyph"]
    assert order.valence is Valence.MIXED
    assert "sword" in order.lesson.lower()
    field = BY_ID["field_construction_opens_from_the_town_disc"]
    assert field.valence is Valence.GOOD
    assert "spend" in field.lesson.lower()


def test_generated_skill_markdown_fits_the_inject_budget():
    root = Path(__file__).resolve().parents[2] / "overlay" / "agent_skills"
    for name in ("campaign_info_sources", "campaign_learnings"):
        skill = yaml.safe_load((root / f"{name}.yaml").read_text(encoding="utf-8"))
        body = (root / f"{name}.md").read_text(encoding="utf-8")
        assert len(body) <= skill["inject"]["max_chars"], name
