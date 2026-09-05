"""Tests for the wiki exporter's guards.

Every case here corresponds to something the exporter got wrong in a real run
against the live wiki, and each failed silently rather than raising:

* the depth-3 category walk left the game entirely and collected Catholicism,
  Islam, Orthodoxy and Buddhism, none of which are in Rome
* two of the four shipped seed category names did not exist, returning no pages
* `slugify` maps distinct titles onto one filename, so one page overwrites another
* `prop=` queries return truncated lists behind a continuation token
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

wiki_export = pytest.importorskip("wiki_export")

is_rome_scoped = wiki_export.is_rome_scoped
topic_check = wiki_export.topic_check
unique_slug = wiki_export.unique_slug


@pytest.mark.parametrize(
    "name",
    [
        "Category:Rome: Total War",
        "Category:Total War: Rome Remastered",
        "Category:Rome: Total War: Barbarian Invasion",
        "Category:Rome: Total War: Alexander",
        "Category:Units (Rome: Total War)",
        "Category:Settlements (Total War: Rome Remastered)",
        "Category:Rome: Total War unit types",
    ],
)
def test_rome_categories_are_in_scope(name):
    assert is_rome_scoped(name)


@pytest.mark.parametrize(
    "name",
    [
        # Shared across the whole franchise, so its name says nothing about Rome.
        "Category:Religion",
        # A different game whose numbers would read as authoritative and be wrong.
        "Category:Total War: Rome II",
        "Category:Total War: Rome II units",
        "Category:Medieval II: Total War",
        "Category:Empire: Total War gameplay mechanics",
        "Category:Napoleon: Total War gameplay mechanics",
        "Category:Total War: Shogun 2 gameplay mechanics",
        "Category:Total War: Attila",
        "Category:Total War: Warhammer",
        "Category:Total War: Three Kingdoms",
        # Maintenance categories carry no game scope at all.
        "Category:Articles needing expansion",
    ],
)
def test_foreign_and_generic_categories_are_fenced_off(name):
    assert not is_rome_scoped(name)


def test_rome_two_is_not_mistaken_for_rome():
    # "Rome II" contains "Rome", so an inclusion-only test admits the wrong game.
    assert is_rome_scoped("Category:Rome: Total War factions")
    assert not is_rome_scoped("Category:Total War: Rome II factions")


@pytest.mark.parametrize(
    "cat",
    [
        # Genuine Barbarian Invasion content whose names never mention Rome. A
        # name-based allowlist fenced all of these off in a real run.
        "Category:Celtic Units",
        "Category:Berber Units",
        "Category:Romano-British Units",
        "Category:Emergent factions",
        "Category:Sassanid Empire (Barbarian Invasion) Units",
    ],
)
def test_faction_subcategories_are_still_walked(cat):
    assert wiki_export.should_walk(cat)


@pytest.mark.parametrize(
    "cat",
    [
        "Category:Total War: Rome II units",
        "Category:Medieval II: Total War",
        "Category:Articles needing expansion",
        "Category:Rome: Total War imagery",
        "Category:Unit cards (Rome: Total War)",
        "Category:Screenshots (Rome: Total War)",
        "Category:Rome: Total War Navboxes",
    ],
)
def test_foreign_and_valueless_categories_are_not_walked(cat):
    assert not wiki_export.should_walk(cat)


def test_the_walk_is_broad_but_pages_are_validated():
    # The design: reach Category:Religion, then reject its members individually,
    # because no name-based rule separates it from Category:Celtic Units.
    assert wiki_export.should_walk("Category:Religion")
    off_topic, _, _ = topic_check({"title": "Catholicism", "categories": ["Category:Religion"]})
    assert off_topic
    kept, _, _ = topic_check(
        {"title": "Kerns", "categories": ["Category:Rome: Total War: Barbarian Invasion units"]}
    )
    assert not kept


@pytest.mark.parametrize(
    "title",
    [
        # Each of these was excluded by a bare-token denylist, and each is real
        # content in this game. The words double as other games' names.
        "Pharaoh's Guards",
        "Pharaoh's Bowmen",
        "Attila the Hun",
        "Arena",
        "Troy",
    ],
)
def test_rome_vocabulary_that_doubles_as_another_games_name_is_kept(title):
    rec = {"title": title, "categories": ["Category:Units (Rome: Total War)"]}
    off_topic, _, _ = topic_check(rec)
    assert not off_topic, f"{title} is Rome content and must not be excluded"


def test_a_title_naming_another_game_vetoes_its_categories():
    # The wiki filed a Rome II unit under a Rome 1 category. Accepting a page because
    # some category matched let it through despite the title saying otherwise.
    rec = {
        "title": "Ilyrian Levies (Total War: Rome II)",
        "categories": [
            "Category:Rome: Total War Illyria units",
            "Category:Total War: Rome II Ardiaei units",
        ],
    }
    off_topic, foreign, _ = topic_check(rec)
    assert off_topic
    assert foreign


def test_a_mixed_page_is_kept_and_marked_mixed():
    rec = {
        "title": "Rebels",
        "categories": [
            "Category:Empire: Total War factions",
            "Category:Factions (Medieval II: Total War)",
            "Category:Rome: Total War factions",
        ],
    }
    off_topic, foreign, mixed = topic_check(rec)
    assert not off_topic, "it does cover Rome, so the Rome content is not discarded"
    assert mixed, "but its numbers are not necessarily Rome's"
    assert len(foreign) == 2


def test_a_purely_rome_page_is_not_marked_mixed():
    rec = {"title": "Hastati", "categories": ["Category:Units (Rome: Total War)"]}
    off_topic, foreign, mixed = topic_check(rec)
    assert not off_topic and not mixed and foreign == []


def test_a_shared_page_is_kept_but_flagged():
    # `Religion` is a direct member of a Rome mechanics category while also being
    # tagged Empire, Napoleon and Shogun 2. Dropping it would hide the overlap;
    # treating it as a Rome fact would be wrong.
    rec = {
        "title": "Religion",
        "categories": [
            "Category:Empire: Total War gameplay mechanics",
            "Category:Napoleon: Total War gameplay mechanics",
            "Category:Total War: Shogun 2 gameplay mechanics",
            "Category:Religion",
        ],
    }
    off_topic, foreign, _ = topic_check(rec)
    assert off_topic
    assert "Empire: Total War gameplay mechanics" in foreign
    assert "Total War: Shogun 2 gameplay mechanics" in foreign


def test_a_page_named_for_the_game_counts_as_on_topic():
    # Some pages carry only maintenance categories but are unambiguous by title.
    rec = {"title": "Rome: Total War", "categories": ["Category:Articles needing images"]}
    off_topic, _, _ = topic_check(rec)
    assert not off_topic


def test_missing_categories_do_not_raise():
    off_topic, foreign, mixed = topic_check({"title": "Whatever", "categories": None})
    assert off_topic and foreign == [] and not mixed


def test_an_undercategorised_rome_page_is_a_known_false_positive():
    # `Slingers (Celts)` is a real Barbarian Invasion unit whose wiki page carries only
    # ["Article stubs", "Celtic Units"] and so fails the category test. Recording the
    # limitation here rather than loosening the rule: the fix is provenance tracking
    # during the walk, and exclusions are written to excluded.json for exactly this
    # kind of review.
    rec = {"title": "Slingers (Celts)", "categories": ["Category:Article stubs",
                                                       "Category:Celtic Units"]}
    off_topic, _, _ = topic_check(rec)
    assert off_topic, "documents current behaviour, not desired behaviour"


def test_distinct_titles_never_share_a_slug():
    taken = {}
    a = unique_slug("Rome: Total War", taken)
    b = unique_slug("Rome Total War", taken)
    assert a != b, "punctuation-only differences must not collide"


def test_the_same_title_always_gets_the_same_slug():
    # Re-running the export must overwrite each page in place rather than shuffling
    # pages between files.
    first = unique_slug("Hastati", {})
    again = unique_slug("Hastati", {})
    assert first == again
    taken = {}
    unique_slug("Hastati", taken)
    assert unique_slug("Hastati", taken) == first


def test_slug_of_an_unnameable_title_is_stable():
    taken = {}
    one = unique_slug("!!!", taken)
    assert one
    assert unique_slug("!!!", taken) == one


class _FakeApi:
    """Returns a `prop=` response split across two continuations."""

    def __init__(self):
        self.calls = 0

    def get(self, params):
        self.calls += 1
        if self.calls == 1:
            return {
                "query": {"pages": [{"title": "Hastati", "categories": [{"title": "A"}]}]},
                "continue": {"clcontinue": "next"},
            }
        return {
            "query": {"pages": [{"title": "Hastati", "categories": [{"title": "B"}]}]}
        }


def test_prop_continuations_are_merged_not_truncated():
    api = _FakeApi()
    merged = wiki_export.Api.pages_merged(api, {"action": "query"})
    titles = [c["title"] for c in merged["Hastati"]["categories"]]
    assert titles == ["A", "B"], "a single request returns only the first slice"
    assert api.calls == 2
