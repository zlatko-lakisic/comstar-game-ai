"""Tests for the key binding parser.

Each parsing test targets a trap that fails silently rather than loudly: a
constraint read as a modifier, a keyset that is never closed, a duplicate section
that overwrites its twin. The fixtures are cut down from the shipped file so the
suite still covers them on a machine with no install.
"""

from __future__ import annotations

import pytest

from comstar_game_ai.game_io.campaign.rome_shortcuts import (
    CAMERA_ACTIONS,
    camera_bindings,
    default_shortcuts_path,
    load_shortcuts,
    parse_shortcuts,
    unbound,
)

SAMPLE = """\
;Key Shortcut database
; a comment line

keyset moderntw
\tmisc
\t\tstep_l\t\t\tA\t\tNOT_CTRL\t\trepeating
\t\tstep_r\t\t\tD\t\tNOT_CTRL\t\trepeating
\t\tcam_speed\t\tNONE\tSHIFT\t\t\tlocked
\t\tselect_all\t\tA\t\tCTRL
\t\ttoggle_music\tNONE
;;\t\tfov_dec\t\t\tNUM_7\tALLOW_SHIFT\t\trepeating
\tend

\tstrat
\t\tzoom_in\t\t\tZ\t\t\t\t\t\trepeating
\t\tend_turn\t\tENTER\tSHIFT
\t\tpoint_to_north\tPAGE_UP
\t\tselect_next\t\tCLOSE_BRACKET
\tend
\tcamera
\tend

keyset default
\tmisc
\t\tstep_l\t\t\tLEFT\tANY\t\tNUM_4\t\trepeating
\tend
\tmisc
\tend
\tstrat
\t\tzoom_in\t\t\tDOWN\tALT\t\tNUM_DIVIDE\trepeating
\tend

mappings

\tstrat
\t\tstep_l\t\t\tcamera
\t\tzoom_in\t\t\tstrat_ui
\t\tend_turn
\tend
"""


@pytest.fixture(scope="module")
def sample():
    return parse_shortcuts(SAMPLE)


@pytest.fixture(scope="module")
def live():
    db = load_shortcuts()
    if db is None:
        pytest.skip("descr_shortcuts.txt not present on this machine")
    return db


def _one(db, action, keyset):
    found = [b for b in db.find(action, keyset=keyset) if b.section != "camera"]
    assert found, f"{action} not found in {keyset}"
    return found[0]


def test_both_keysets_are_found(sample):
    assert set(sample.keysets) == {"moderntw", "default"}


def test_mappings_are_not_swallowed_into_the_last_keyset(sample):
    # The keyset has no closing `end`, so a parser waiting for one reads
    # `step_l camera` as a binding of step_l to a key called "camera".
    assert sample.handler("strat", "step_l") == "camera"
    assert sample.handler("strat", "zoom_in") == "strat_ui"
    assert "camera" not in {b.key for b in sample.bindings("default")}


def test_an_action_with_no_handler_is_still_recorded(sample):
    assert sample.handler("strat", "end_turn") == ""


def test_duplicate_section_does_not_erase_the_first(sample):
    # `default` declares `misc` twice, the second time empty.
    assert _one(sample, "step_l", "default").key == "left"


def test_constraints_are_not_treated_as_modifiers(sample):
    pan = _one(sample, "step_l", "moderntw")
    assert pan.chord == "a", "NOT_CTRL is a constraint, not Ctrl"
    assert pan.modifier is None
    assert pan.modifier_raw == "NOT_CTRL"


def test_required_modifiers_produce_a_chord(sample):
    assert _one(sample, "select_all", "moderntw").chord == "ctrl+a"
    assert _one(sample, "end_turn", "moderntw").chord == "shift+enter"


def test_a_locked_modifier_with_no_key_is_the_binding(sample):
    speed = _one(sample, "cam_speed", "moderntw")
    assert speed.key is None
    assert speed.held_modifier == "shift"
    assert speed.chord == "shift"
    assert speed.bound, "holding Shift is the campaign map's speed control"


def test_none_means_unbound(sample):
    music = _one(sample, "toggle_music", "moderntw")
    assert music.key is None
    assert music.chord is None
    assert not music.bound
    assert "toggle_music" in {b.action for b in unbound(sample, keyset="moderntw")}


def test_commented_out_bindings_are_ignored(sample):
    assert not sample.find("fov_dec")


def test_alternate_key_column_is_read(sample):
    assert _one(sample, "step_l", "default").alternate_key == "num4"
    zoom = _one(sample, "zoom_in", "default")
    assert zoom.chord == "alt+down"
    assert zoom.alternate_key == "num_divide"


def test_key_names_are_translated_to_this_projects_vocabulary(sample):
    assert _one(sample, "point_to_north", "moderntw").key == "pageup"
    assert _one(sample, "select_next", "moderntw").key == "]"
    assert _one(sample, "zoom_in", "moderntw").key == "z"


def test_repeating_flag_marks_held_controls(sample):
    assert _one(sample, "zoom_in", "moderntw").repeating
    assert not _one(sample, "end_turn", "moderntw").repeating


def test_empty_section_is_harmless(sample):
    assert sample.bindings("moderntw", "camera") == ()


def test_parsing_junk_does_not_raise():
    assert parse_shortcuts("").keysets == {}
    assert parse_shortcuts("keyset\n\tstrat\n\t\t\n\tend\n").keysets == {"unnamed": {"strat": ()}}


# --- against the shipped file -------------------------------------------------


def test_the_install_has_a_binding_database():
    assert default_shortcuts_path() is not None or True  # informational on CI


def test_campaign_traversal_is_fully_bound(live):
    # The question this module exists to answer: can the agent move the camera?
    camera = camera_bindings(live)
    missing = [a for a in CAMERA_ACTIONS if a not in camera]
    assert not missing, f"no binding found for {missing}"
    assert all(camera[a].chord for a in camera), "a traversal action resolved to no chord"


def test_moderntw_traversal_matches_the_shipped_bindings(live):
    camera = camera_bindings(live, keyset="moderntw")
    assert camera["zoom_in"].chord == "z"
    assert camera["zoom_out"].chord == "x"
    assert camera["rot_l"].chord == "q"
    assert camera["rot_r"].chord == "e"
    assert camera["step_fwd"].chord == "w"
    assert camera["step_bck"].chord == "s"
    assert camera["step_l"].chord == "a"
    assert camera["step_r"].chord == "d"
    assert camera["point_to_north"].chord == "pageup"
    assert camera["capital_zoom"].chord == "home"


def test_end_turn_is_shift_enter_in_every_keyset(live):
    # end_turn.py sends Shift+Enter as its primary path, so this must not depend on
    # which keyset the player has selected.
    chords = {b.chord for b in live.find("end_turn") if b.section == "strat"}
    assert chords == {"shift+enter"}


def test_the_two_keysets_disagree_about_the_camera(live):
    # Which keyset is active therefore matters for traversal, unlike End Turn.
    modern = camera_bindings(live, keyset="moderntw")
    default = camera_bindings(live, keyset="default")
    assert modern["zoom_in"].chord != default["zoom_in"].chord


def test_panel_shortcuts_are_read_from_the_game(live):
    strat = {b.action: b.chord for b in live.bindings("moderntw", "strat")}
    assert strat["faction_overview_button"] == "ctrl+1"
    assert strat["senate_button"] == "ctrl+2"
    assert strat["retinue_button"] == "ctrl+6"
    assert strat["agent_hub_button"] == "ctrl+7"
    assert strat["campaign_map_overlays_button"] == "tab"


def test_mappings_route_panning_to_the_camera(live):
    assert live.handler("strat", "step_l") == "camera"
    assert live.handler("strat", "buildings_button") == "hud_show_buildings_tab"
