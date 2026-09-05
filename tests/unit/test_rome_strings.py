"""Parsing Rome's shipped string tables.

The fixtures reproduce the exact shapes found in the shipped files, including the
two that would corrupt data silently: conditional comments and mid-line comments.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from comstar_game_ai.game_io.campaign.rome_strings import (
    COMMENT_CHAR,
    decode_string_file,
    load_campaign_tables,
    load_string_table,
    lookup,
    parse_string_table,
)

TOOLTIPS = (
    f"{COMMENT_CHAR} Text file converted with loc_parser\n"
    "{TMT_SETTLEMENT_INCOME}\t\t\tSettlement Income\n"
    "{TMT_LOYALTY_TOOLTIP_REVOLTING}\t\t\tLoyalty: Revolting\n"
    "{TMT_CONSTRUCTION_HELP}\t\tLeft click to add to queue, right click for information\n"
)


def test_parses_key_and_value():
    table = parse_string_table(TOOLTIPS, name="tooltips")
    assert table.entries["TMT_SETTLEMENT_INCOME"] == "Settlement Income"
    assert table.entries["TMT_LOYALTY_TOOLTIP_REVOLTING"] == "Loyalty: Revolting"
    assert len(table) == 3


def test_the_declaring_comment_line_is_not_an_entry():
    table = parse_string_table(TOOLTIPS)
    assert table.comments_enabled
    assert not any("loc_parser" in value for value in table.entries.values())


def test_a_value_keeps_its_internal_punctuation():
    """"Loyalty: Revolting" must not be split on the colon."""
    table = parse_string_table(TOOLTIPS)
    assert table.entries["TMT_LOYALTY_TOOLTIP_REVOLTING"].count(":") == 1


def test_mid_line_comments_are_stripped():
    """shortcut.txt ships one. Without this the shortcut is named
    "Strategy menu ¬ Mid line comment"."""
    text = (
        f"{COMMENT_CHAR} Comments are marked with whatever character this is\n"
        f"{{strat}}\t\t\tStrategy menu\t\t{COMMENT_CHAR} Mid line comment, just to test\n"
    )
    table = parse_string_table(text, name="shortcut")
    assert table.entries["strat"] == "Strategy menu"


def test_comments_are_ignored_when_the_first_line_does_not_declare_one():
    """date_format.txt and credits.txt ship without a declaring comment, so the
    comment character is ordinary content there."""
    text = f"Credits\n{{author}}\tSome {COMMENT_CHAR} literal\n"
    table = parse_string_table(text)
    assert not table.comments_enabled
    assert table.entries["author"] == f"Some {COMMENT_CHAR} literal"


def test_comment_lines_between_entries_are_skipped():
    text = (
        f"{COMMENT_CHAR} header\n"
        "{first}\tOne\n"
        f"{COMMENT_CHAR}*******************************\n"
        f"{COMMENT_CHAR}*   THIS FILE GONE FOR LOCALISATION!!!\n"
        "{second}\tTwo\n"
    )
    table = parse_string_table(text)
    assert table.entries == {"first": "One", "second": "Two"}


def test_wrapped_values_are_joined():
    """Long descriptions in export_buildings and export_advice wrap."""
    text = (
        f"{COMMENT_CHAR} header\n"
        "{long_desc}\tThe first part of the sentence\n"
        "and the continuation of it.\n"
    )
    table = parse_string_table(text)
    assert table.entries["long_desc"] == (
        "The first part of the sentence and the continuation of it."
    )


def test_a_blank_line_ends_a_wrapped_value():
    """Otherwise an unrelated later line gets glued onto the previous entry."""
    text = f"{COMMENT_CHAR} header\n{{a}}\tAlpha\n\nstray text\n{{b}}\tBeta\n"
    table = parse_string_table(text)
    assert table.entries == {"a": "Alpha", "b": "Beta"}


def test_a_comment_line_ends_a_wrapped_value():
    text = f"{COMMENT_CHAR} header\n{{a}}\tAlpha\n{COMMENT_CHAR} note\nstray\n{{b}}\tBeta\n"
    table = parse_string_table(text)
    assert table.entries["a"] == "Alpha"


def test_an_empty_value_is_kept_as_empty_not_dropped():
    """export_advice_feral.txt is full of defined-but-blank keys; the key existing
    is itself information."""
    text = f"{COMMENT_CHAR} header\n{{defined_but_blank}}\t\n{{next}}\tValue\n"
    table = parse_string_table(text)
    assert table.entries["defined_but_blank"] == ""
    assert "defined_but_blank" in table


def test_the_first_definition_of_a_repeated_key_wins():
    text = f"{COMMENT_CHAR} h\n{{dup}}\tFirst\n{{dup}}\tSecond\n"
    assert parse_string_table(text).entries["dup"] == "First"


def test_an_empty_file_is_not_an_error():
    table = parse_string_table("")
    assert len(table) == 0
    assert not table.comments_enabled


def test_utf16_with_a_bom_decodes():
    raw = TOOLTIPS.encode("utf-16")
    assert raw[:2] == b"\xff\xfe"
    assert decode_string_file(raw).lstrip("\ufeff").startswith(COMMENT_CHAR)


def test_utf8_also_decodes():
    """Defensive: a hand-edited or modded table may not be UTF-16."""
    assert "Settlement Income" in decode_string_file(TOOLTIPS.encode("utf-8"))


def test_undecodable_bytes_do_not_raise():
    assert isinstance(decode_string_file(b"\x81\x82\x83"), str)


def test_load_string_table_round_trips_a_real_shaped_file(tmp_path: Path):
    path = tmp_path / "tooltips.txt"
    path.write_bytes(TOOLTIPS.encode("utf-16"))
    table = load_string_table(path)
    assert table.name == "tooltips"
    assert table.path == path
    assert table.entries["TMT_SETTLEMENT_INCOME"] == "Settlement Income"


def test_load_campaign_tables_reads_what_is_present_and_skips_the_rest(tmp_path: Path):
    (tmp_path / "tooltips.txt").write_bytes(TOOLTIPS.encode("utf-16"))
    (tmp_path / "shortcut.txt").write_bytes(
        f"{COMMENT_CHAR} h\n{{strat}}\tStrategy menu\n".encode("utf-16")
    )
    tables = load_campaign_tables(tmp_path)
    assert set(tables) == {"tooltips", "shortcut"}


def test_load_campaign_tables_on_an_empty_directory_is_empty_not_fatal(tmp_path: Path):
    assert load_campaign_tables(tmp_path) == {}


def test_lookup_prefers_the_more_specific_table(tmp_path: Path):
    """A key in both tooltips and menu_english means the campaign meaning."""
    (tmp_path / "tooltips.txt").write_bytes(
        f"{COMMENT_CHAR} h\n{{shared_key}}\tCampaign meaning\n".encode("utf-16")
    )
    (tmp_path / "menu_english.txt").write_bytes(
        f"{COMMENT_CHAR} h\n{{shared_key}}\tMenu meaning\n".encode("utf-16")
    )
    tables = load_campaign_tables(tmp_path)
    assert lookup(tables, "shared_key") == ("tooltips", "Campaign meaning")


def test_lookup_returns_none_for_an_unknown_key(tmp_path: Path):
    assert lookup({}, "nothing") is None


# --- against the real install, when it is present ----------------------------


@pytest.fixture(scope="module")
def real_tables():
    from comstar_game_ai.game_io.campaign.rome_strings import default_text_dir

    directory = default_text_dir()
    if directory is None:
        pytest.skip("Rome Remastered text directory not found on this machine")
    return load_campaign_tables(directory)


def test_the_real_tooltips_table_is_substantial(real_tables):
    assert len(real_tables["tooltips"]) > 150


def test_the_real_cursor_action_vocabulary_is_present(real_tables):
    """These are the campaign map's verbs, and the atlas is built around them."""
    actions = real_tables["cursor_action_tooltips"]
    for key in ("enter_settlement", "diplomacy_mission", "spy_mission", "embark_army"):
        assert key in actions, f"{key} missing from cursor_action_tooltips"
    assert "Right click" in actions.entries["enter_settlement"]


def test_no_real_value_retains_a_comment_marker(real_tables):
    """The mid-line comment trap, checked against every shipped campaign table."""
    for name, table in real_tables.items():
        for key, value in table.entries.items():
            if table.comments_enabled:
                assert COMMENT_CHAR not in value, f"{name}.{key} kept a comment: {value!r}"


def test_no_real_key_is_wrapped_in_braces(real_tables):
    """A key parsed as "{foo}" rather than "foo" means the regex slipped."""
    for name, table in real_tables.items():
        for key in table.entries:
            assert not key.startswith("{"), f"{name} produced a braced key: {key!r}"
