"""Tests for the Event Log dock (Alerts / News / Reports / Missions)."""

from __future__ import annotations

import itertools

from comstar_game_ai.game_io.campaign.left_dock import (
    BY_ID,
    CLOSE_X,
    FILTER_CENTRE,
    PANEL_RIGHT,
    TABS,
    closed_centres,
    open_centres,
)


def test_ids_are_unique_and_in_screen_order():
    assert len(BY_ID) == len(TABS) == 4
    assert [tab.id for tab in TABS] == ["alerts", "news", "reports", "missions"]


def test_closed_discs_stack_on_the_left_edge():
    xs = [tab.closed_centre[0] for tab in TABS]
    ys = [tab.closed_centre[1] for tab in TABS]
    assert all(x < 0.03 for x in xs)
    assert ys == sorted(ys)
    assert xs == [xs[0]] * 4


def test_open_tabs_sit_just_past_the_parchment_edge():
    for tab in TABS:
        assert tab.open_centre[0] > PANEL_RIGHT
        assert tab.open_centre[1] == tab.closed_centre[1]


def test_neighbouring_tabs_do_not_share_a_centre():
    for a, b in itertools.combinations(TABS, 2):
        assert a.closed_centre != b.closed_centre
        assert a.open_centre != b.open_centre


def test_tooltips_are_the_words_read_off_the_screen():
    assert BY_ID["alerts"].tooltip_title == "Alerts"
    assert "empire" in BY_ID["alerts"].tooltip_body.lower()
    assert BY_ID["news"].tooltip_title == "News"
    assert "factions" in BY_ID["news"].tooltip_body.lower()
    assert BY_ID["reports"].tooltip_title == "Reports"
    assert "End Of Turn Report" in BY_ID["reports"].tooltip_body
    assert BY_ID["missions"].tooltip_title == "Missions"
    assert "Senate" in BY_ID["missions"].tooltip_body


def test_empty_tabs_do_not_invent_footer_button_names():
    for tab_id in ("alerts", "news", "reports"):
        text = BY_ID[tab_id].what_it_shows.lower()
        assert "no " in text
        assert "burn" not in text
        assert "mark all" not in text


def test_missions_is_the_senate_card_not_the_senate_window():
    note = BY_ID["missions"].note.lower()
    assert "senate_mission_card" in note
    assert "ctrl+2" in note


def test_close_x_sits_on_the_parchment_corner():
    x, y = CLOSE_X
    assert abs(x - PANEL_RIGHT) < 0.01
    assert 0.07 < y < 0.09


def test_filter_is_left_of_the_close_x_and_named():
    assert FILTER_CENTRE[0] < CLOSE_X[0]
    assert abs(FILTER_CENTRE[1] - CLOSE_X[1]) < 0.02


def test_centre_helpers_follow_the_tabs():
    assert closed_centres() == tuple(tab.closed_centre for tab in TABS)
    assert open_centres() == tuple(tab.open_centre for tab in TABS)
