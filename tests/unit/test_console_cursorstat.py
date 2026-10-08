"""Console-band reader for show_cursorstat.

Train-session frames live under data/runtime/cursorstat_sessions and are not
the locked test split. Those checks only guard the abstain rule on frames
the templates were cut from.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from PIL import Image

from comstar_game_ai.game_io.campaign.console_cursorstat import (
    _DIGIT_ART,
    _LINE_H,
    _MAP_X_LIMIT,
    _MAP_Y_LIMIT,
    _MIN_DIGIT_RATIO,
    _accept_numbers,
    _glyph_fault,
    _read_numbers,
    _row_bits,
    _six_px_line_tops,
    coordinate_has_unmatched_glyph,
    parse_position_line,
    read_console_cursorstat,
)

TRAIN = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "runtime"
    / "cursorstat_sessions"
    / "20261003-pass"
)
TRAIN16 = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "runtime"
    / "cursorstat_sessions"
    / "20261006-train16x"
)

# Glyphs on that session's pos lines, read off the image.
TRAIN_XY = {
    "anchor.png": (88, 83),
    "anchor_repeat.png": (88, 83),
    "east.png": (96, 82),
    "north.png": (87, 90),
    "settlement.png": (96, 82),
}


def test_parse_live_console_lines():
    assert parse_position_line("pos 87, 83, region id 15 (Liguria)") == (87, 83)
    assert parse_position_line("pos 95, 83, region id 15 (Umbria)") == (95, 83)
    assert parse_position_line("pos 87, 90, region id 36 (Venetia)") == (87, 90)


def test_parse_position_x_form():
    assert parse_position_line("position: x 120, y 116, region id 96") == (120, 116)


def test_parse_ignores_bare_pairs_and_keeps_the_last_line():
    text = "\n".join(
        [
            "gold 5000, treasury 12",
            "position: x 1, y 2, region id 3",
            "pos 10, 20, region id 4",
        ]
    )
    assert parse_position_line(text) == (10, 20)
    assert parse_position_line("date 200, 100") is None
    assert parse_position_line("") is None


def test_refuses_other_window_sizes():
    reading = read_console_cursorstat(Image.new("RGB", (100, 80)))
    assert reading.xy is None
    assert reading.confidence is None
    assert "1280x720" in reading.reason

    wide = Image.new("RGB", (1920, 1080))
    refused = read_console_cursorstat(wide)
    assert refused.xy is None
    assert "1920x1080" in refused.reason


def _paint_pair(x_digits: str, y_digits: str, extra: list[int] | None = None) -> Image.Image:
    """A 1280×720 frame whose pos-line digits are the given strings.

    A trailing ink block makes each row tall enough to be a console line.
    It starts at x=120, past the digits. ``extra`` columns are full ink
    inside the coordinate span and belong to no glyph.
    """
    image = Image.new("RGB", (1280, 720), (0, 0, 0))
    px = image.load()
    top = 117
    # Trailing block, three blank columns past the digits, so the line
    # detector sees 6 px of text and the block is not a third coordinate.
    for x in range(120, 133):
        for dy in range(_LINE_H):
            px[x, top + dy] = (255, 255, 255)
    cursor = 76

    def paint(digit: str) -> None:
        nonlocal cursor
        art = _DIGIT_ART[digit][0]
        width = len(art[0])
        for dy, row in enumerate(art):
            for dx, ch in enumerate(row):
                if ch == "#":
                    px[cursor + dx, top + dy] = (255, 255, 255)
        cursor += width

    for digit in x_digits:
        paint(digit)
    if extra:
        for col in extra:
            for dy in range(_LINE_H):
                px[col, top + dy] = (255, 255, 255)
    cursor += 1
    px[cursor, top + _LINE_H - 1] = (255, 255, 255)
    cursor += 2
    for digit in y_digits:
        paint(digit)
    return image


def test_a_complete_number_is_returned():
    reading = read_console_cursorstat(_paint_pair("88", "83"))
    assert reading.xy == (88, 83)
    assert reading.confidence is not None
    assert reading.confidence > _MIN_DIGIT_RATIO


@pytest.mark.parametrize(
    "x_digits,y_digits",
    [("100", "90"), ("84", "80"), ("141", "44"), ("44", "12")],
)
def test_adjacent_glyphs_are_not_shortened(x_digits: str, y_digits: str):
    reading = read_console_cursorstat(_paint_pair(x_digits, y_digits))
    assert reading.xy == (int(x_digits), int(y_digits))
    assert reading.confidence == 1.0


def test_unexplained_ink_abstains_without_a_confidence():
    # The column sits on the coordinate span and is not a digit we painted.
    reading = read_console_cursorstat(_paint_pair("10", "90", extra=[83]))
    assert reading.xy is None
    assert reading.confidence is None
    assert reading.reason.startswith("unexplained ink")


def test_reads_outside_the_map_are_refused():
    assert _MAP_X_LIMIT == 255
    assert _MAP_Y_LIMIT == 156
    too_wide = read_console_cursorstat(_paint_pair("255", "10"))
    assert too_wide.xy is None
    assert too_wide.confidence is None
    assert "outside the map" in too_wide.reason
    too_tall = read_console_cursorstat(_paint_pair("10", "156"))
    assert too_tall.xy is None
    assert too_tall.confidence is None
    assert "outside the map" in too_tall.reason


def test_truncated_live_frame_no_longer_returns_a_confident_short_number():
    path = (
        Path(__file__).resolve().parents[2]
        / "data"
        / "runtime"
        / "homography_sessions"
        / "zoom0"
        / "grid_09.png"
    )
    if not path.is_file():
        pytest.skip(f"missing {path}")
    reading = read_console_cursorstat(Image.open(path))
    assert reading.xy is None
    assert reading.confidence is None
    assert "unexplained ink" in reading.reason


def _lock_module():
    path = Path(__file__).resolve().parents[2] / "scripts" / "lock_cursorstat_gate.py"
    spec = importlib.util.spec_from_file_location("lock_cursorstat_gate", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_arm_geometry_flags_a_step_the_neighbors_do_not_share():
    lock = _lock_module()
    rows = [
        {"file": "sweep0_00.png", "xy": [10, 5], "label_source": "operator"},
        {"file": "sweep0_02.png", "xy": [11, 5], "label_source": "operator"},
        {"file": "sweep0_04.png", "xy": [15, 5], "label_source": "operator"},
        {"file": "sweep0_24.png", "xy": [10, 20], "label_source": "operator"},
        {"file": "sweep0_26.png", "xy": [10, 18], "label_source": "operator"},
        {"file": "sweep0_28.png", "xy": [10, 17], "label_source": "operator"},
    ]
    breaks = lock.geometry_breaks("session", rows, [])
    assert [item["frame"] for item in breaks] == ["sweep0_04.png"]
    assert breaks[0]["previous"]["xy"] == [11, 5]
    assert breaks[0]["next"] is None
    assert breaks[0]["step"] == 4
    steady = [
        {"file": "sweep0_00.png", "xy": [93, 53], "label_source": "operator"},
        {"file": "sweep0_02.png", "xy": [94, 53], "label_source": "operator"},
        {"file": "sweep0_04.png", "xy": [95, 53], "label_source": "operator"},
    ]
    assert lock.geometry_breaks("session", steady, []) == []
    jumped = [
        {"file": "sweep0_00.png", "xy": [91, 53], "label_source": "operator"},
        {"file": "sweep0_02.png", "xy": [95, 53], "label_source": "operator"},
        {"file": "sweep0_04.png", "xy": [96, 53], "label_source": "operator"},
    ]
    fixed = lock.geometry_breaks(
        "session",
        jumped,
        [{"frame": "sweep0_00.png", "new_xy": [94, 53]}],
    )
    assert fixed == []


def test_lock_requires_every_place_and_the_adjacent_numbers():
    missing = _lock_module()._missing([(88, 83)])
    assert "adjacent number 100" in missing
    assert "a three-digit coordinate" in missing
    assert "hundreds digit 2 in x" in missing
    labels = [(digit * 10 + digit, digit * 10 + ((digit + 3) % 10)) for digit in range(10)]
    labels.extend([(100, 44), (141, 84), (200, 100)])
    assert _lock_module()._missing(labels) == []


@pytest.mark.parametrize("name,expected", list(TRAIN_XY.items()))
def test_train_session_reads(name: str, expected: tuple[int, int]):
    path = TRAIN / name
    if not path.is_file():
        pytest.skip(f"missing {path}")
    reading = read_console_cursorstat(Image.open(path))
    assert reading.xy == expected
    assert reading.reason == ""
    assert reading.confidence is not None
    assert reading.confidence > _MIN_DIGIT_RATIO
    assert coordinate_has_unmatched_glyph(Image.open(path)) is False


def test_first_glyph_later_than_77_is_a_missing_leading_digit():
    assert _glyph_fault(["4", "42"], [(80, 3), (86, 3), (90, 3)]) == (
        "unexplained ink; missing leading digit"
    )
    assert _glyph_fault(["44", "42"], [(76, 3), (80, 3), (86, 3), (90, 3)]) is None
    assert _glyph_fault(["44", "42"], [(77, 3), (81, 3), (87, 3), (91, 3)]) is None
    assert _glyph_fault(["4", "42"], [(75, 3), (80, 3), (84, 3)]) is None


def test_train16x_drop_refuses_leading_zero_and_overlap():
    path = TRAIN16 / "sweep0_00.png"
    if not path.is_file():
        pytest.skip(f"missing {path}")
    gray = Image.open(path).convert("L")
    tops = _six_px_line_tops(gray)
    assert tops
    parsed = _read_numbers(_row_bits(gray, tops[0]))
    numbers, _confidence, spans = parsed
    assert len(numbers[0]) > 1 and numbers[0].startswith("0")
    assert any(
        spans[index + 1][0] - (spans[index][0] + spans[index][1]) < 0
        for index in range(len(spans) - 1)
    )
    refused = _accept_numbers(_row_bits(gray, tops[0]), parsed)
    assert refused.xy is None
    assert refused.confidence is None
    assert refused.reason.startswith("unexplained ink")
    assert f"leading zero in {numbers[0]}" in refused.reason
    assert "glyph gap -1" in refused.reason
    reading = read_console_cursorstat(Image.open(path))
    assert reading.xy == (160, 54)
    assert reading.confidence is not None
    assert reading.confidence > _MIN_DIGIT_RATIO


def test_train16x_intact_leading_one_still_reads():
    path = TRAIN16 / "sweep0_02.png"
    if not path.is_file():
        pytest.skip(f"missing {path}")
    reading = read_console_cursorstat(Image.open(path))
    assert reading.xy == (161, 54)
    assert reading.reason == ""
