"""Tests for the campaign UI atlas.

The load-bearing test here is `test_every_name_key_resolves_in_the_shipped_tables`.
The atlas stores string keys instead of English text so it cannot drift from the
game, but that only holds if the keys are real; an invented key is silently
name-less. It needs the install, so it skips rather than fails on CI.
"""

from __future__ import annotations

import pytest

from comstar_game_ai.game_io.campaign import ui_atlas
from comstar_game_ai.game_io.campaign.rome_shortcuts import load_shortcuts
from comstar_game_ai.game_io.campaign.rome_strings import (
    default_text_dir,
    load_campaign_tables,
)
from comstar_game_ai.game_io.campaign.ui_atlas import (
    ATLAS,
    BY_ID,
    Dismiss,
    PanelClass,
    PanelGeometry,
    Status,
    match_geometry,
)


@pytest.fixture(scope="module")
def tables():
    if default_text_dir() is None:
        pytest.skip("Rome text directory not present on this machine")
    loaded = load_campaign_tables()
    if not loaded:
        pytest.skip("no campaign string tables could be read")
    return loaded


def test_ids_are_unique():
    assert len(BY_ID) == len(ATLAS)


def test_every_entry_has_a_dismissal_strategy():
    for entry in ATLAS:
        assert entry.dismiss, f"{entry.id} has no way out"


def test_only_notices_are_non_blocking():
    # Decision panels block for a different reason than obstructing ones, but they
    # do block: the turn waits for an answer.
    for entry in ATLAS:
        assert entry.blocking is (entry.panel_class is not PanelClass.NOTICE)


def test_decision_panels_have_no_close_button_and_others_do():
    # The invariant that resolved the corpus: a close-X search coming back empty on
    # a blocking panel means "decision panel", not "detector failed".
    for entry in ui_atlas.verified():
        if entry.panel_class is PanelClass.DECISION:
            assert not entry.expects_close_x
            assert entry.geometry.close_x is None, f"{entry.id} should have no close X"
        else:
            assert entry.expects_close_x
            assert entry.geometry.close_x is not None, f"{entry.id} needs a close X"


def test_decision_panels_are_answered_not_dismissed():
    for entry in ATLAS:
        if entry.panel_class is not PanelClass.DECISION:
            continue
        assert entry.dismiss == (Dismiss.DECISION_BUTTON,), (
            f"{entry.id} must be answered; there is no button to dismiss it"
        )


def test_notices_may_be_left_open_but_obstructing_panels_may_not():
    for entry in ATLAS:
        leaves_open = Dismiss.LEAVE_OPEN in entry.dismiss
        if entry.panel_class is PanelClass.OBSTRUCTING:
            assert not leaves_open, f"{entry.id} blocks input and cannot be left open"


def test_verified_entries_carry_geometry_and_evidence():
    for entry in ui_atlas.verified():
        assert entry.geometry is not None, f"{entry.id} is verified without geometry"
        assert entry.evidence, f"{entry.id} is verified without evidence"


def test_unseen_entries_are_the_guided_capture_worklist():
    unseen = ui_atlas.unseen()
    assert unseen, "nothing left to capture would mean the atlas is complete"
    for entry in unseen:
        assert entry.geometry is None, f"{entry.id} has geometry but is marked unseen"
        assert entry.opened_by, f"{entry.id} cannot be captured without a way to open it"


def test_escape_is_only_trusted_where_the_game_documents_it():
    # The advisor's own button reads "Dismiss advice [ESC]". Everything else that
    # lists Escape must try the close X first.
    for entry in ATLAS:
        if Dismiss.ESCAPE not in entry.dismiss:
            continue
        if entry.id == "advisor":
            continue
        assert entry.dismiss[0] is Dismiss.CLOSE_X, (
            f"{entry.id} reaches for Escape before the close X"
        )


def test_building_browser_spans_the_centre_and_notices_do_not():
    assert BY_ID["building_browser"].geometry.spans_centre()
    assert not BY_ID["senate_mission_card"].geometry.spans_centre()
    assert not BY_ID["left_dock_notice"].geometry.spans_centre()


def test_every_name_key_resolves_in_the_shipped_tables(tables):
    missing = [e.id for e in ATLAS if e.name_key and e.name(tables) is None]
    assert not missing, f"atlas keys absent from the game's tables: {missing}"


def test_a_panel_without_a_name_key_must_explain_itself():
    # Remastered added UI the original tables never named. That is allowed, but it
    # has to be stated, otherwise a missing key is indistinguishable from an oversight.
    for entry in ATLAS:
        if not entry.name_key:
            assert entry.note, f"{entry.id} has no name key and no explanation"
            assert entry.opened_by, f"{entry.id} is unnamed and has no way to open it"


def test_shortcut_actions_exist_in_the_binding_database():
    shortcuts = load_shortcuts()
    if shortcuts is None:
        pytest.skip("descr_shortcuts.txt not present on this machine")
    for entry in ATLAS:
        if not entry.shortcut_action:
            continue
        found = shortcuts.find(entry.shortcut_action)
        assert found, f"{entry.id} names action {entry.shortcut_action!r} which is unbound"


def test_the_panels_reachable_by_keyboard_are_recorded():
    by_action = {e.shortcut_action for e in ATLAS if e.shortcut_action}
    # The Ctrl+1..7 cluster is the campaign map's whole panel bar; missing one means
    # a panel the agent cannot reach without hunting for its button.
    for action in (
        "faction_overview_button",
        "senate_button",
        "diplomacy_overview_button",
        "finances_button",
        "lists_button",
        "retinue_button",
        "agent_hub_button",
    ):
        assert action in by_action, f"no atlas entry opens via {action}"


def test_resolved_names_are_the_games_own_words(tables):
    assert BY_ID["building_browser"].name(tables) == "Building Browser"
    assert "finances" in BY_ID["finance_window"].name(tables).lower()
    assert "ESC" in BY_ID["advisor"].name(tables)


def test_match_identifies_the_building_browser_from_measured_edges():
    match = match_geometry(0.26, 0.74, 0.21)
    assert match is not None
    assert match.entry.id == "building_browser"
    assert match.distance == pytest.approx(0.0, abs=1e-9)


def test_match_tolerates_small_measurement_drift():
    match = match_geometry(0.28, 0.72, 0.23)
    assert match is not None
    assert match.entry.id == "building_browser"


def test_match_identifies_the_two_decision_panels():
    diplomacy = match_geometry(0.20, 0.76, 0.13)
    assert diplomacy is not None
    assert diplomacy.entry.id == "diplomatic_negotiations"
    battle = match_geometry(0.16, 0.83, 0.35)
    assert battle is not None
    assert battle.entry.id == "battle_deployment"


def test_diplomacy_right_edge_varies_across_the_corpus():
    # The nine frames measured 0.75 to 0.79 on the right edge; all nine must land on
    # the same entry or the corpus is not actually resolved.
    for right in (0.75, 0.76, 0.77, 0.79):
        match = match_geometry(0.20, right, 0.13)
        assert match is not None and match.entry.id == "diplomatic_negotiations"


def test_diplomacy_is_not_confused_with_the_building_browser():
    # They overlap heavily; the top edge (0.13 vs 0.21) is what separates them.
    assert match_geometry(0.20, 0.76, 0.13).entry.id == "diplomatic_negotiations"
    assert match_geometry(0.26, 0.74, 0.21).entry.id == "building_browser"


def test_match_returns_none_for_an_unknown_panel():
    # A tall narrow panel on the right belongs to no verified entry. Guessing here
    # would hide the panels guided capture exists to find.
    assert match_geometry(0.80, 0.99, 0.30) is None


def test_match_prefers_the_closer_entry():
    # The two left-dock entries overlap; the measured edges decide between them.
    senate = match_geometry(0.00, 0.16, 0.07)
    notice = match_geometry(0.03, 0.33, 0.07)
    assert senate is not None and senate.entry.id == "senate_mission_card"
    assert notice is not None and notice.entry.id == "left_dock_notice"


def test_geometry_spans_centre_is_exclusive_at_the_edges():
    assert not PanelGeometry(left=0.5, right=0.9, top=0.1).spans_centre()
    assert not PanelGeometry(left=0.1, right=0.5, top=0.1).spans_centre()
    assert PanelGeometry(left=0.49, right=0.51, top=0.1).spans_centre()


def test_status_and_class_vocabularies_are_closed():
    assert {s.value for s in Status} == {"verified", "unseen"}
    assert {c.value for c in PanelClass} == {"decision", "notice", "obstructing"}
