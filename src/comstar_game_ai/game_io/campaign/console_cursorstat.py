"""Read ``show_cursorstat`` from the console band of a campaign frame.

The command is painted into the console and is not copied into the logs.
Coordinates come from templates of that bitmap font.

Confidence is the worst accepted glyph's template agreement. It says nothing
about whether every ink column was used. A dropped digit used to leave a
shorter number whose surviving glyphs still scored 0.78, above the floor.
A read now abstains when any ink column in the coordinate span is outside
an accepted glyph, and the refusal carries no confidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from PIL import Image

# Last matching line wins. Accepts the live console form
# ``pos 87, 83, region id 15`` and ``position: x 120, y 116, region id 96``.
_POSITION_LINE = re.compile(
    r"(?i)pos(?:ition)?\s*:?\s*(?:x\s+)?(-?\d+)\s*,\s*(?:y\s+)?"
    r"(-?\d+)\s*,\s*region\s*id\s+\d+"
)

_EXPECTED_SIZE = (1280, 720)
_INK = 60
# A live stroke's top rows can sit just under 60, so the strict grid
# drops a digit and the unexplained-ink check refuses the short number.
# The same 6 px line is rebuilt from 59 down to this cutoff, and the
# first complete read is kept. A line that already reads at 60 is not
# rebuilt. Saved frames that are truly truncated still refuse.
_INK_FAINT_FLOOR = 46
_LINE_H = 6
# Train session 20261003-pass, measured only on 6 px text runs.
# The weakest correct digit (the 8 in 83) matches at 0.667.
# The strongest wrong class at that same cell matches at 0.556.
# The y=91 false window that reads 77,77 is not a 6 px run, so it is
# not a candidate. Abstain at or below the gap, which keeps 0.667.
# This floor accepts or rejects one glyph. It is not a completeness
# score: a truncated "10" still cleared it at 0.78 because the dropped
# digit was not in the minimum.
_MIN_DIGIT_RATIO = 0.60
_MIN_CLASS_MARGIN = 0.10
# map_regions.tga is 255×156. A settlement pixel is (x, height-1-y),
# so a live coordinate is inside x < 255 and y < 156. Measured from
# that file. The radar box (200, 150) is smaller than the map.
_MAP_X_LIMIT = 255
_MAP_Y_LIMIT = 156
# 8 keeps the live pos line. Its second row has 9 ink pixels in x=60–140,
# one under the old minimum, which split the glyph and hid the line.
# Train frames still have their 6 px run at this minimum.
_ROW_INK_MIN = 8
_DIGIT_X0 = 60
_DIGIT_X1 = 140

# Each digit may have more than one exemplar cut from train frames.
# 4 is from 20261003-digits3 rand_07.png, x=80–82, the cell between 83 and 85.
_DIGIT_ART: dict[str, tuple[tuple[str, ...], ...]] = {
    "0": (("##.", "#.#", "#.#", "#.#", "#.#", "##."),),
    "1": (
        (".#", ".#", "##", "##", "##", ".#"),
        # Serifed 1 from 20261003-digits2 rand_07, x=81–82. Not the test set.
        ("##", ".#", ".#", ".#", ".#", "##"),
    ),
    "2": (("###", "#.#", "..#", ".#.", "...", "###"),),
    "3": (("###", "#.#", "..#", ".##", "..#", "###"),),
    "4": ((".#.", ".#.", ".#.", "##.", "###", ".#."),),
    "5": (("###", "#..", "##.", "..#", "..#", "###"),),
    "6": ((".##", "#..", "###", "#.#", "#.#", ".##"),),
    "7": (("###", "..#", "...", ".#.", ".#.", ".#."),),
    "8": (
        ("###", "#.#", "##.", "###", "#.#", "###"),
        ("###", "#.#", "###", "#.#", "#.#", "#.#"),
    ),
    "9": ((".##.", "#..#", "#..#", "####", "#..#", "###."),),
}


@dataclass(frozen=True)
class ConsoleCursorstat:
    """Map coordinates from the console, or a refusal with a reason."""

    xy: tuple[int, int] | None
    confidence: float | None
    reason: str = ""


def parse_position_line(text: str) -> tuple[int, int] | None:
    """Return the last ``pos`` / ``position`` line in ``text``, or None.

    A bare pair of numbers does not match. Gold totals and dates in a wide
    crop must not become a cursor position.
    """
    found: tuple[int, int] | None = None
    for line in (text or "").splitlines() or [text or ""]:
        for match in _POSITION_LINE.finditer(line):
            found = (int(match.group(1)), int(match.group(2)))
    return found


def read_console_cursorstat(image: Image.Image) -> ConsoleCursorstat:
    """Read the cursor position painted in the top console band."""
    reason = _geometry_reason(image)
    if reason:
        return ConsoleCursorstat(xy=None, confidence=None, reason=reason)
    gray = image.convert("L")
    tops = _six_px_line_tops(gray)
    if not tops:
        return ConsoleCursorstat(
            xy=None,
            confidence=None,
            reason="console glyph height is not 6 px; templates are for 1280x720",
        )
    success: ConsoleCursorstat | None = None
    failure: ConsoleCursorstat | None = None
    for top in tops:
        reading = _read_at(gray, top)
        if reading.xy is None:
            failure = reading
            continue
        success = reading
    if success is not None:
        return success
    if failure is not None:
        return failure
    return ConsoleCursorstat(xy=None, confidence=None, reason="no position line")


def _geometry_reason(image: Image.Image) -> str:
    width, height = image.size
    if (width, height) != _EXPECTED_SIZE:
        return (
            f"frame is {width}x{height}; reader requires "
            f"{_EXPECTED_SIZE[0]}x{_EXPECTED_SIZE[1]}"
        )
    return ""


# One row of a live pos line can fall under the row minimum (measured 7
# where the minimum is 8) and split the glyph. A window may include that
# row only when no exact 6 px run exists.
_ROW_INK_WEAK = 4


def _six_px_line_tops(gray: Image.Image, row_min: int = _ROW_INK_MIN) -> list[int]:
    """Starts of console text runs that are exactly one template tall."""
    px = gray.load()
    y0 = 80
    inks: list[int] = []
    for y in range(y0, 150):
        inks.append(sum(1 for x in range(_DIGIT_X0, _DIGIT_X1) if px[x, y] >= _INK))
    flags = [ink >= row_min for ink in inks]
    tops: list[int] = []
    i = 0
    while i < len(flags):
        if not flags[i]:
            i += 1
            continue
        j = i
        while j < len(flags) and flags[j]:
            j += 1
        if j - i == _LINE_H:
            tops.append(y0 + i)
        i = j
    if tops:
        return tops
    for i in range(len(inks) - _LINE_H + 1):
        window = inks[i : i + _LINE_H]
        if sum(ink >= row_min for ink in window) >= _LINE_H - 1 and all(
            ink >= _ROW_INK_WEAK for ink in window
        ):
            tops.append(y0 + i)
    return tops


def _read_at(gray: Image.Image, top: int) -> ConsoleCursorstat:
    judged = _judge_line(_row_bits(gray, top))
    if judged.xy is not None or not judged.reason.startswith("unexplained"):
        return judged
    # A higher cutoff can drop a leading digit and still look complete
    # ("142" becomes "2"). Keep the complete read with the most digits.
    best = judged
    best_digits = -1
    for ink in range(_INK - 1, _INK_FAINT_FLOOR - 1, -1):
        faint = _judge_line(_row_bits(gray, top, ink))
        if faint.xy is None:
            continue
        digits = len(str(faint.xy[0])) + len(str(faint.xy[1]))
        if digits > best_digits:
            best = faint
            best_digits = digits
    return best


def _judge_line(grid: list[list[int]]) -> ConsoleCursorstat:
    judged = _accept_numbers(grid, _read_numbers(grid))
    if judged.xy is not None or not judged.reason.startswith("unexplained"):
        return judged
    covered = _cover_single_orphan(grid)
    if covered is None:
        return judged
    alt = _accept_numbers(grid, covered)
    if alt.xy is None:
        return judged
    return alt


def _accept_numbers(
    grid: list[list[int]],
    parsed: tuple[list[str], float | None, list[tuple[int, int]]],
) -> ConsoleCursorstat:
    numbers, confidence, spans = parsed
    if (
        len(numbers) < 2
        or not all(1 <= len(token) <= 3 for token in numbers[:2])
        or confidence is None
        or not spans
    ):
        return ConsoleCursorstat(
            xy=None,
            confidence=None,
            reason="no position line",
        )
    xy = (int(numbers[0]), int(numbers[1]))
    if _unexplained_columns(grid, spans):
        return ConsoleCursorstat(
            xy=None,
            confidence=None,
            reason=f"unexplained ink; refused {xy[0]}, {xy[1]}",
        )
    if not _inside_map(xy):
        return ConsoleCursorstat(
            xy=None,
            confidence=None,
            reason=(
                f"coordinate {xy[0]}, {xy[1]} is outside the map "
                f"0..{_MAP_X_LIMIT - 1}, 0..{_MAP_Y_LIMIT - 1}"
            ),
        )
    if confidence <= _MIN_DIGIT_RATIO:
        return ConsoleCursorstat(
            xy=None,
            confidence=None,
            reason=(
                f"confidence {confidence:.3f} is at or below {_MIN_DIGIT_RATIO:.2f}"
            ),
        )
    return ConsoleCursorstat(xy=xy, confidence=confidence, reason="")


def _inside_map(xy: tuple[int, int]) -> bool:
    return 0 <= xy[0] < _MAP_X_LIMIT and 0 <= xy[1] < _MAP_Y_LIMIT


def _row_bits(gray: Image.Image, y0: int, ink: int = _INK) -> list[list[int]]:
    px = gray.load()
    width = gray.width
    return [
        [1 if px[x, y0 + dy] >= ink else 0 for x in range(width)]
        for dy in range(_LINE_H)
    ]


def _digit_hits(grid: list[list[int]]) -> list[tuple[int, float, str, int]]:
    width = len(grid[0])
    hits: list[tuple[int, float, str, int]] = []
    for x in range(50, min(width, 220)):
        match = _best_digit(grid, x)
        if match is not None:
            ratio, digit, tw = match
            hits.append((x, ratio, digit, tw))
    return hits


def _filter_hits(
    hits: list[tuple[int, float, str, int]],
) -> list[tuple[int, float, str, int]]:
    kept: list[tuple[int, float, str, int]] = []
    for x, ratio, digit, tw in hits:
        if any(
            abs(x - ox) < max(tw, ot) - 1 and o_ratio > ratio
            for ox, o_ratio, _od, ot in hits
        ):
            continue
        if any(
            ox <= x < ox + ot and o_ratio >= ratio and not (ox == x and od == digit)
            for ox, o_ratio, od, ot in kept
        ):
            continue
        kept.append((x, ratio, digit, tw))
    kept.sort()
    return kept


def _read_numbers(
    grid: list[list[int]],
) -> tuple[list[str], float | None, list[tuple[int, int]]]:
    return _assemble(grid, _filter_hits(_digit_hits(grid)))


def _assemble(
    grid: list[list[int]], kept: list[tuple[int, float, str, int]]
) -> tuple[list[str], float | None, list[tuple[int, int]]]:
    numbers: list[str] = []
    ratios: list[float] = []
    spans: list[tuple[int, int]] = []
    current = ""
    current_ratios: list[float] = []
    current_spans: list[tuple[int, int]] = []
    prev_end: int | None = None
    for x, ratio, digit, tw in kept:
        if prev_end is not None and (
            x - prev_end > 2 or _comma_between(grid, prev_end, x)
        ):
            if current:
                numbers.append(current)
                ratios.extend(current_ratios)
                spans.extend(current_spans)
            current = ""
            current_ratios = []
            current_spans = []
            if len(numbers) >= 2:
                break
        if len(numbers) < 2:
            current += digit
            current_ratios.append(ratio)
            current_spans.append((x, tw))
        prev_end = x + tw
    if current and len(numbers) < 2:
        numbers.append(current)
        ratios.extend(current_ratios)
        spans.extend(current_spans)
    if not ratios:
        return numbers, None, spans
    return numbers, min(ratios), spans


def _single_orphan(grid: list[list[int]], spans: list[tuple[int, int]]) -> int | None:
    if not spans:
        return None
    covered: set[int] = set()
    for x, tw in spans:
        covered.update(range(x, x + tw))
    start = _extend_back(grid, min(covered))
    end = _extend_forward(grid, max(x + tw for x, tw in spans))
    extra = [
        col
        for col in range(start, end)
        if _column_kind(grid, col) == "ink" and col not in covered
    ]
    if len(extra) != 1:
        return None
    return extra[0]


def _cover_single_orphan(
    grid: list[list[int]],
) -> tuple[list[str], float | None, list[tuple[int, int]]] | None:
    """Replace a narrow digit when one leftover column is a wider glyph.

    A live ``0`` can score lower than the ``1`` made from its right two
    columns. The leftover left column then refuses a complete coordinate.
    A dropped digit with no covering glyph, as on a truncated ``10``,
    is left refused.
    """
    _numbers, _confidence, spans = _read_numbers(grid)
    col = _single_orphan(grid, spans)
    if col is None:
        return None
    cover: tuple[int, float, str, int] | None = None
    for x, ratio, digit, tw in _digit_hits(grid):
        if x <= col < x + tw and ratio > _MIN_DIGIT_RATIO:
            if cover is None or tw > cover[3]:
                cover = (x, ratio, digit, tw)
    if cover is None:
        return None
    cx, _cr, _cd, ct = cover
    kept = [
        hit
        for hit in _filter_hits(_digit_hits(grid))
        if hit[0] >= cx + ct or cx >= hit[0] + hit[3]
    ]
    kept.append(cover)
    kept.sort()
    return _assemble(grid, kept)


def _comma_between(grid: list[list[int]], start: int, end: int) -> bool:
    """True when a comma sits in a gap too small to split on width alone.

    Live text paints ``109,80`` with the comma one column from the 8.
    That gap is 2, and the old rule only split when the gap was wider.
    """
    return any(_only_bottom(grid, col) for col in range(start, end))


def _column_kind(grid: list[list[int]], x: int) -> str:
    if not any(grid[dy][x] for dy in range(_LINE_H)):
        return "blank"
    if _only_bottom(grid, x):
        return "comma"
    return "ink"


def _unexplained_columns(grid: list[list[int]], spans: list[tuple[int, int]]) -> bool:
    """True when coordinate ink sits outside every accepted glyph.

    The span grows by one blank column backward, so a dropped leading
    digit is included and the word ``pos`` (two blank columns away) is
    not. It grows forward across three blank columns, which keeps a
    digit that sits past the last glyph and the comma after it, and
    stops before ``region``.
    """
    covered: set[int] = set()
    for x, tw in spans:
        covered.update(range(x, x + tw))
    start = min(covered)
    end = max(covered) + 1
    start = _extend_back(grid, start)
    end = _extend_forward(grid, end)
    return any(
        _column_kind(grid, col) == "ink" and col not in covered
        for col in range(start, end)
    )


def _extend_back(grid: list[list[int]], start: int) -> int:
    x = start - 1
    blanks = 0
    while x >= 50:
        if _column_kind(grid, x) == "blank":
            blanks += 1
            if blanks > 1:
                break
            x -= 1
            continue
        start = x
        blanks = 0
        x -= 1
    return start


def _extend_forward(grid: list[list[int]], end: int) -> int:
    width = min(len(grid[0]), 220)
    x = end
    blanks = 0
    while x < width:
        if _column_kind(grid, x) == "blank":
            blanks += 1
            if blanks > 3:
                break
            x += 1
            continue
        end = x + 1
        blanks = 0
        x += 1
    return end


def coordinate_has_unmatched_glyph(image: Image.Image) -> bool:
    """True when a pos-line number glyph matches no known digit.

    The capture script uses this to stop once a frame can supply the
    missing 4. Region-id digits are outside the band. A miss is False:
    the known templates still explain every glyph, or the line is absent.
    """
    if image.size != _EXPECTED_SIZE:
        return False
    gray = image.convert("L")
    # 8 keeps a row whose ink is just under the reader's floor of 12.
    tops = _six_px_line_tops(gray, row_min=8)
    if not tops:
        return False
    return _band_has_unmatched(_row_bits(gray, tops[-1]), 74, 99)


def _band_has_unmatched(grid: list[list[int]], x0: int, x1: int) -> bool:
    width = len(grid[0])
    x1 = min(x1, width)
    runs: list[tuple[int, int]] = []
    run_start: int | None = None
    prev = -1
    for x in range(x0, x1):
        ink = any(grid[dy][x] for dy in range(_LINE_H))
        if not ink:
            continue
        if run_start is None or x - prev > 1:
            if run_start is not None:
                runs.append((run_start, prev + 1))
            run_start = x
        prev = x
    if run_start is not None:
        runs.append((run_start, prev + 1))
    return any(_run_unmatched(grid, start, end) for start, end in runs)


def _only_bottom(grid: list[list[int]], x: int) -> bool:
    """The comma is a dot on the baseline and sometimes touches a digit."""
    return grid[_LINE_H - 1][x] == 1 and all(grid[dy][x] == 0 for dy in range(_LINE_H - 1))


def _run_unmatched(grid: list[list[int]], start: int, end: int) -> bool:
    """A comma is one column. Wider ink must be a sequence of known digits.

    A comma is stripped. Anything left over is an unknown digit.
    """
    while start < end and _only_bottom(grid, start):
        start += 1
    while end > start and _only_bottom(grid, end - 1):
        end -= 1
    if end - start < 2:
        return False
    pos = start
    while pos < end:
        if not any(grid[dy][pos] for dy in range(_LINE_H)):
            pos += 1
            continue
        match = _raw_best_digit(grid, pos, end)
        if match is None or match[0] < 0.50:
            return end - pos >= 2
        pos += match[1]
    return False


def _raw_best_digit(
    grid: list[list[int]], x: int, limit: int
) -> tuple[float, int] | None:
    best_ratio = -1.0
    best_tw = 0
    for exemplars in _DIGIT_ART.values():
        for art in exemplars:
            tw = len(art[0])
            if x + tw > limit or len(art) != _LINE_H:
                continue
            score = 0
            total = tw * _LINE_H
            for dy, row in enumerate(art):
                for dx, ch in enumerate(row):
                    ink = grid[dy][x + dx]
                    score += 1 if (ch == "#") == bool(ink) else -1
            ratio = score / total
            if ratio > best_ratio:
                best_ratio = ratio
                best_tw = tw
    if best_tw == 0:
        return None
    return best_ratio, best_tw


def _best_digit(grid: list[list[int]], x: int) -> tuple[float, str, int] | None:
    width = len(grid[0])
    ranked: list[tuple[float, str, int]] = []
    for digit, exemplars in _DIGIT_ART.items():
        best_ratio = -1.0
        best_tw = 0
        for art in exemplars:
            tw = len(art[0])
            if x + tw > width or len(art) != _LINE_H:
                continue
            score = 0
            total = tw * _LINE_H
            for dy, row in enumerate(art):
                for dx, ch in enumerate(row):
                    ink = grid[dy][x + dx]
                    score += 1 if (ch == "#") == bool(ink) else -1
            ratio = score / total
            if ratio > best_ratio:
                best_ratio = ratio
                best_tw = tw
        if best_tw:
            ranked.append((best_ratio, digit, best_tw))
    if not ranked:
        return None
    ranked.sort(reverse=True)
    best_ratio, digit, tw = ranked[0]
    second = ranked[1][0] if len(ranked) > 1 else -1.0
    if best_ratio <= _MIN_DIGIT_RATIO:
        return None
    if best_ratio - second < _MIN_CLASS_MARGIN:
        return None
    return best_ratio, digit, tw
