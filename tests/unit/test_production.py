"""Tests for Julii produce cost and per-turn run cost."""

from __future__ import annotations

from comstar_game_ai.game_io.campaign.production import (
    BUILDINGS,
    BY_BUILDING,
    BY_FIELD,
    BY_UNIT,
    FIELD_WORKS,
    TREASURY_SPENDS,
    UNITS,
)


def test_ids_are_unique():
    assert len(BY_UNIT) == len(UNITS)
    assert len(BY_BUILDING) == len(BUILDINGS)
    assert len(BY_FIELD) == len(FIELD_WORKS)


def test_buildings_have_no_upkeep():
    assert all(item.upkeep == 0 for item in BUILDINGS)


def test_live_arretium_prices_are_recorded():
    assert BY_UNIT["Peasants"].recruit == 100
    assert BY_UNIT["Hastati"].recruit == 440
    assert BY_UNIT["Hastati"].upkeep == 170
    assert BY_BUILDING["Practice Range"].live_construct == 1080
    assert BY_FIELD["watchtower"].construct == 200
    assert BY_FIELD["fort"].construct == 500


def test_treasury_spends_sum_to_the_live_drop():
    start = TREASURY_SPENDS[0][2]
    end = TREASURY_SPENDS[-1][3]
    spent = sum(row[1] for row in TREASURY_SPENDS)
    assert start - spent == end
    assert start - end == 2700
