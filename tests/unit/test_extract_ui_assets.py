"""Tests for the install asset extractor, focused on the EDU join.

The join is the part with real failure modes: card stems match either of two
different EDU fields, the files may be UTF-16, and three mod roots define
overlapping keys. Everything else in the extractor is a directory walk.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "tools"))

from extract_ui_assets import (  # noqa: E402
    DEFAULT_INSTALL,
    build_edu_index,
    iter_ui_art,
    iter_unit_art,
    parse_edu,
    read_game_text,
)

SAMPLE_EDU = """\
;; comment header
type             roman hastati
dictionary       roman_hastati      ; Hastati
category         infantry
class            light
soldier          roman_hastati, 40, 0, 1

type             barb archer
category         infantry
class            missile
"""


@pytest.fixture
def edu_file(tmp_path):
    path = tmp_path / "export_descr_unit.txt"
    path.write_text(SAMPLE_EDU, encoding="utf-8")
    return str(path)


def test_parse_edu_reads_each_unit_block(edu_file):
    entries = parse_edu(edu_file)
    assert [e["type"] for e in entries] == ["roman hastati", "barb archer"]
    assert entries[0]["dictionary"] == "roman_hastati"
    assert entries[0]["category"] == "infantry"
    assert entries[0]["class"] == "light"


def test_parse_edu_truncates_comma_separated_fields(edu_file):
    # soldier carries a count and scale after the model name; only the name is wanted.
    assert parse_edu(edu_file)[0]["soldier"] == "roman_hastati"


def test_parse_edu_tolerates_a_unit_with_no_dictionary(edu_file):
    assert "dictionary" not in parse_edu(edu_file)[1]


def test_parse_edu_ignores_trailing_comments(edu_file):
    assert parse_edu(edu_file)[0]["dictionary"] == "roman_hastati"


def test_read_game_text_decodes_utf16_with_bom(tmp_path):
    path = tmp_path / "utf16.txt"
    path.write_bytes(b"\xff\xfe" + "type roman hastati".encode("utf-16-le"))
    assert read_game_text(str(path)) == "type roman hastati"


def test_read_game_text_decodes_plain_utf8(tmp_path):
    path = tmp_path / "utf8.txt"
    path.write_text("type roman hastati", encoding="utf-8")
    assert read_game_text(str(path)) == "type roman hastati"


def test_edu_index_registers_both_the_dictionary_and_the_type_alias(tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    (root / "export_descr_unit.txt").write_text(SAMPLE_EDU, encoding="utf-8")

    index, per_mod = build_edu_index(str(tmp_path))

    assert per_mod == {"base": 2}
    # A card named for the dictionary key resolves...
    assert index["roman_hastati"]["type"] == "roman hastati"
    # ...and so does one named for the underscored type, which is the only handle
    # units without a dictionary field have.
    assert index["barb_archer"]["type"] == "barb archer"


def test_edu_index_attributes_a_shared_key_to_the_earliest_mod(tmp_path):
    for sub in ("", "bi"):
        root = tmp_path / sub / "data"
        root.mkdir(parents=True)
        (root / "export_descr_unit.txt").write_text(SAMPLE_EDU, encoding="utf-8")

    index, per_mod = build_edu_index(str(tmp_path))

    assert per_mod == {"base": 2, "bi": 2}
    assert index["roman_hastati"]["mod"] == "base"


# --- Live install ------------------------------------------------------------
# Skipped on machines without the game; these assert against real shipped data.

live = pytest.mark.skipif(
    not os.path.isdir(DEFAULT_INSTALL), reason="game install not present"
)


@live
def test_live_install_defines_units_in_all_three_mods():
    _, per_mod = build_edu_index(DEFAULT_INSTALL)
    assert set(per_mod) == {"base", "bi", "alexander"}
    assert all(count > 100 for count in per_mod.values())


@live
def test_live_cards_mostly_resolve_to_a_named_unit():
    index, _ = build_edu_index(DEFAULT_INSTALL)
    stems = {key for _, _, _, _, key, _, _ in iter_unit_art(DEFAULT_INSTALL)}
    named = stems & set(index)
    # The remainder is art the install ships but no unit references. It is kept and
    # simply left unnamed, so this guards the join, not the extraction.
    assert len(named) / len(stems) > 0.7


@live
def test_live_info_portraits_share_the_card_naming_so_the_two_join():
    art = list(iter_unit_art(DEFAULT_INSTALL))
    cards = {k for _, a, _, _, k, _, _ in art if a == "units"}
    infos = {k for _, a, _, _, k, _, _ in art if a == "unit_info"}
    # A card and its portrait must reduce to the same unit_key, otherwise the two
    # would land in the index as unrelated rows.
    assert len(cards & infos) > 300


@live
def test_live_classic_art_mirrors_the_remastered_set():
    art = list(iter_unit_art(DEFAULT_INSTALL))
    modern = {(m, f, s) for m, a, f, s, _, _, _ in art if a == "units"}
    classic = {(m, f, s) for m, a, f, s, _, _, _ in art if a == "units_classic"}
    # Both are extracted because the classic UI toggle decides which is drawn.
    assert modern == classic


@live
def test_live_no_two_source_images_claim_the_same_output_path():
    # Regression: reducing the filename to the join key made '#alan_horse_archers'
    # and 'alan_horse_archers_info' collide inside one directory, so 16 images were
    # overwritten. The output name must stay one-to-one with the source.
    seen = {}
    for mod, art, faction, stem, _, _, src in iter_unit_art(DEFAULT_INSTALL):
        dest = (mod, art, faction, stem)
        assert dest not in seen, "%s written from both %s and %s" % (
            "/".join(dest), seen.get(dest), src)
        seen[dest] = src


@live
def test_live_kind_follows_the_filename_not_the_directory():
    art = list(iter_unit_art(DEFAULT_INSTALL))
    # Several unit_info directories also hold cards, so the directory alone is not
    # a reliable signal of what an image is.
    in_info = [(k, s) for _, a, _, s, k, kind, _ in art
               if a == "unit_info" and kind == "card"]
    assert in_info, "expected at least one card misfiled under unit_info"


@live
def test_live_cursor_art_is_present_and_small():
    ui = [row for row in iter_ui_art(DEFAULT_INSTALL) if row[1] == "cursors"]
    names = {os.path.splitext(rel)[0] for _, _, rel, _ in ui}
    # These join to cursor_action_tooltips.txt, which is what makes a cursor match
    # mean something rather than merely being a shape.
    assert {"anim_attack", "anim_moveto"} <= names
