"""Tests for settlement identification.

Two jobs. The parser tests pin it against the four tooltips actually captured in
game, one per standing, so a refactor cannot quietly stop recognising a real
tooltip. The palette tests defend the caveats: the module claims certain colours are
separable and certain others collide, and those claims are load-bearing — an agent
that trusts a colour the module said was ambiguous will attack an ally.
"""

from __future__ import annotations

import itertools

import pytest

from comstar_game_ai.game_io.campaign import settlements
from comstar_game_ai.game_io.campaign.rome_strings import load_campaign_tables
from comstar_game_ai.game_io.campaign.settlements import (
    FACTION_LEGEND_COLOURS,
    LABEL_PILL_COLOURS,
    OVERLAY_STATE_COLOURS,
    OVERLAY_STATE_SWATCHES,
    Activity,
    Relation,
    Tier,
    nearest,
    parse_settlement_tooltip,
)

# Transcribed from the captured frames named in each case. Kept verbatim, including the
# trailing hint lines, because the hint lines are themselves signal.
SEGESTA = """Segesta
Ligurian Rebels
Village (At war)
240 0 2 turns
Hold Alt to expand tooltip"""

ARIMINUM = """Ariminum
The House of Julii
Large town
184 1 5 turns
x2 to get further information
Hold Alt to expand tooltip"""

PATAVIUM = """Patavium
Gaul
Large town (Neutral)
294 1 5 turns
Hold Alt to expand tooltip"""

ROME = """Rome (Capital)
S.P.Q.R.
Minor city (Ally)
606 3 8 turns
Hold Alt to expand tooltip"""


def test_an_enemy_settlement_is_read_as_hostile():
    """hov_segesta.png: a rebel village we are at war with."""
    reading = parse_settlement_tooltip(SEGESTA)
    assert reading is not None
    assert reading.name == "Segesta"
    assert reading.owner == "Ligurian Rebels"
    assert reading.tier is Tier.VILLAGE
    assert reading.relation is Relation.AT_WAR
    assert reading.relation.is_hostile
    assert not reading.owner_is_us


def test_our_own_settlement_has_no_standing_suffix_and_offers_management():
    """hov_ariminum.png: the absence of a suffix is what marks it ours."""
    reading = parse_settlement_tooltip(ARIMINUM)
    assert reading is not None
    assert reading.owner == "The House of Julii"
    assert reading.tier is Tier.LARGE_TOWN
    assert reading.relation is Relation.OURS
    assert reading.owner_is_us
    # The double-click hint appears only on settlements we can open, so it is an
    # independent confirmation of ownership that needs no faction name at all.
    assert reading.manageable


def test_a_neutral_settlement_is_not_confused_with_an_enemy():
    """hov_patavium.png: Gaul, neutral on turn 1 and not to be attacked."""
    reading = parse_settlement_tooltip(PATAVIUM)
    assert reading is not None
    assert reading.owner == "Gaul"
    assert reading.relation is Relation.NEUTRAL
    assert not reading.relation.is_hostile
    assert not reading.manageable


def test_an_allied_capital_is_read_as_both_allied_and_a_capital():
    """tt_rome_crest.png: Rome, the case that pins the (Capital) marker."""
    reading = parse_settlement_tooltip(ROME)
    assert reading is not None
    # The marker rides on the name, and must be stripped from it rather than left in.
    assert reading.name == "Rome"
    assert reading.is_capital
    assert reading.owner == "S.P.Q.R."
    assert reading.tier is Tier.MINOR_CITY
    assert reading.relation is Relation.ALLY
    assert not reading.relation.is_hostile
    assert not reading.owner_is_us


def test_every_standing_that_can_appear_is_covered_by_a_captured_case():
    """No standing may be modelled without a real tooltip behind it."""
    covered = {
        parse_settlement_tooltip(text).relation
        for text in (SEGESTA, ARIMINUM, PATAVIUM, ROME)
    }
    assert covered == set(Relation)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "Road\nIncome per turn: 0",  # a real tooltip: the hover that missed Rome
        "Segesta\nLigurian Rebels",
    ],
)
def test_a_tooltip_that_is_not_a_settlement_is_declined(text):
    """Returning None beats inventing a settlement out of a road or an army."""
    assert parse_settlement_tooltip(text) is None


def test_a_road_tooltip_is_not_mistaken_for_a_settlement_when_it_has_enough_lines():
    """crop_rome_tt.png. Three lines, but no tier, so no tier is claimed."""
    reading = parse_settlement_tooltip("Road\nIncome per turn: 0\nHold Alt to expand tooltip")
    assert reading is not None
    assert reading.tier is None
    assert not reading.manageable


def test_tier_keys_all_resolve_against_the_installed_string_tables():
    tables = load_campaign_tables()
    if not tables:
        pytest.skip("no installed string tables to check against")
    for tier in Tier:
        # Every tier is key-backed, so each must come back from the install and must
        # not silently fall through to the observed English.
        assert tier.name_key
        assert tier.label(tables) == tier.observed, f"{tier.name} drifted from the install"


def test_the_tier_key_that_disagrees_with_its_text_is_still_correct():
    """ST_CITY reads 'Minor city'. The mismatch is why entries store keys."""
    tables = load_campaign_tables()
    if not tables:
        pytest.skip("no installed string tables to check against")
    assert Tier.MINOR_CITY.name_key == "ST_CITY"
    assert Tier.MINOR_CITY.label(tables).casefold() == "minor city"


def test_the_two_key_backed_standings_resolve_from_the_install():
    tables = load_campaign_tables()
    if not tables:
        pytest.skip("no installed string tables to check against")
    for relation in (Relation.NEUTRAL, Relation.AT_WAR):
        assert relation.localises
        assert relation.suffix(tables) == relation.observed


def test_ours_and_ally_are_recorded_as_having_no_shipped_string():
    """The gap is real and must stay visible.

    `SMT_ALLIES` reads "Allies" — the overlay legend heading, not the tooltip's
    "Ally". Wiring it in here would look right and would break a localised install.
    """
    assert not Relation.OURS.localises
    assert Relation.OURS.suffix() == ""
    assert not Relation.ALLY.localises
    assert Relation.ALLY.suffix() == "Ally"


def test_the_allies_legend_string_is_not_the_ally_tooltip_string():
    """Enforces the specific confusion the module warns about."""
    tables = load_campaign_tables()
    if not tables:
        pytest.skip("no installed string tables to check against")
    from comstar_game_ai.game_io.campaign.rome_strings import lookup

    found = lookup(tables, "SMT_ALLIES")
    assert found is not None
    assert found[1] != Relation.ALLY.observed


def test_tiers_are_ordered_smallest_first():
    ranks = [tier.rank for tier in Tier]
    assert ranks == sorted(ranks) == list(range(len(Tier)))


def test_every_overlay_state_has_both_a_swatch_and_a_colour():
    assert set(OVERLAY_STATE_SWATCHES) == set(OVERLAY_STATE_COLOURS)
    # Every activity, plus every standing the overlay distinguishes. Our own
    # settlements are coloured by activity rather than standing, so OURS is absent.
    assert set(OVERLAY_STATE_COLOURS) == set(Activity) | {
        Relation.ALLY,
        Relation.AT_WAR,
        Relation.NEUTRAL,
    }


def test_overlay_swatches_sit_inside_the_client_rect():
    for key, (x, y) in OVERLAY_STATE_SWATCHES.items():
        assert 0.0 < x < 1.0, f"{key} has an x outside the frame"
        assert 0.0 < y < 1.0, f"{key} has a y outside the frame"


def test_overlay_state_colours_are_far_enough_apart_to_tell_apart():
    """These drive the read of which settlement needs orders, so they must not blur."""
    for a, b in itertools.combinations(OVERLAY_STATE_COLOURS.items(), 2):
        distance = sum(abs(p - q) for p, q in zip(a[1], b[1]))
        assert distance > 90, f"{a[0]} and {b[0]} are only {distance} apart"


def test_faction_legend_colours_are_distinct():
    for a, b in itertools.combinations(FACTION_LEGEND_COLOURS.items(), 2):
        assert a[1] != b[1], f"{a[0]} and {b[0]} share a colour"


def test_carthage_white_and_idle_white_really_do_collide():
    """The documented trap, enforced so the docstring cannot rot.

    Carthage's faction fill and the 'settlement idle' icon tint are both near-white
    and land within a few units of each other. They are only separable by which
    palette is being read, so anything that matches a pixel against both at once is
    wrong by construction.
    """
    carthage = FACTION_LEGEND_COLOURS["Carthage"]
    idle = OVERLAY_STATE_COLOURS[Activity.IDLE]
    assert sum(abs(a - b) for a, b in zip(carthage, idle)) < 20


def test_the_label_pill_palette_does_not_pretend_to_know_the_allied_pill():
    """Ally was confirmed light blue by eye at distance, never measured cleanly.

    Recording only the three that were measured keeps a guessed RGB out of a table
    an agent would otherwise trust.
    """
    assert set(LABEL_PILL_COLOURS) == {Relation.OURS, Relation.NEUTRAL, Relation.AT_WAR}


def test_our_pill_and_the_neutral_pill_separate_on_the_blue_channel():
    """The whole reason the naive nearest-legend match was abandoned."""
    ours = LABEL_PILL_COLOURS[Relation.OURS]
    neutral = LABEL_PILL_COLOURS[Relation.NEUTRAL]
    assert ours[2] - neutral[2] > 60
    # ...and they are genuinely close in the other two channels, which is why matching
    # them against the overlay legend put both on "neutral".
    assert abs(ours[0] - neutral[0]) < 30


def test_nearest_declines_rather_than_guessing_when_nothing_is_close():
    assert nearest((0, 255, 0), LABEL_PILL_COLOURS, tolerance=60) is None


def test_nearest_finds_the_measured_pill_colours_exactly():
    for relation, rgb in LABEL_PILL_COLOURS.items():
        assert nearest(rgb, LABEL_PILL_COLOURS) is relation


def test_the_owned_hint_pattern_matches_the_captured_wording():
    assert settlements.OWNED_HINT.search("x2 to get further information")
    assert not settlements.OWNED_HINT.search("Hold Alt to expand tooltip")
