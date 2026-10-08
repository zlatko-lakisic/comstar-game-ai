"""Lock the new cursorstat test split. Does not score.

Train sessions stay the ones that supplied templates. Test sessions are
whole captures, never a frame mix from a train session. The lock is
refused until every test frame has a glyph label and the set covers
three-digit coordinates, every digit in every place the map can show,
and the adjacent numbers 100, 84, 141, and 44.

    python scripts/lock_cursorstat_gate.py --test 20261003-gate
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SESSIONS = ROOT / "data" / "runtime" / "cursorstat_sessions"
SPLIT = SESSIONS / "split_v3.json"
_REGRESSION = ROOT / "docs" / "cursorstat-regression-v2.json"

# 20261003-pass supplied every template except 4. The 4 was cut from
# 20261003-digits3. Neither session is a test session.
_TRAIN = ("20261003-pass", "20261003-digits3")
_ADJACENT = (100, 84, 141, 44)
_FRAME_INDEX = re.compile(r"_(\d+)\.png$")
_SWEEP_FRAME = re.compile(r"^(sweep\d+)_(\d+)\.png$")
# Same even-frame subset as scripts/label_cursorstat_gate.py.
_EVEN_ONLY = frozenset(
    {
        "20261006-gate19",
        "20261006-gate20",
        "20261006-gate21",
        "20261006-gate22",
        "20261006-gate23",
        "20261006-gate24",
        "20261008-gate25",
        "20261008-gate26",
    }
)


def _in_test_set(session_id: str, row: dict) -> bool:
    if session_id not in _EVEN_ONLY:
        return True
    match = _FRAME_INDEX.search(str(row.get("file", "")))
    return match is not None and int(match.group(1)) % 2 == 0


def _missing(labels: list[tuple[int, int]]) -> list[str]:
    missing: list[str] = []
    xs = [x for x, _y in labels]
    ys = [y for _x, y in labels]
    if not any(value >= 100 for value in xs + ys):
        missing.append("a three-digit coordinate")
    for place, values in (
        ("x units", [value % 10 for value in xs]),
        ("x tens", [(value // 10) % 10 for value in xs]),
        ("y units", [value % 10 for value in ys]),
        ("y tens", [(value // 10) % 10 for value in ys]),
    ):
        for digit in range(10):
            if digit not in values:
                missing.append(f"digit {digit} in {place}")
    # Map x is 0..254 and map y is 0..155, so the hundreds digit cannot
    # be 3-9. y cannot be 2 either.
    for digit in (0, 1, 2):
        if digit not in [value // 100 for value in xs]:
            missing.append(f"hundreds digit {digit} in x")
    for digit in (0, 1):
        if digit not in [value // 100 for value in ys]:
            missing.append(f"hundreds digit {digit} in y")
    present = set(xs) | set(ys)
    for number in _ADJACENT:
        if number not in present:
            missing.append(f"adjacent number {number}")
    return missing


def _reviewed(row: dict) -> bool:
    """True when the operator typed a pair or marked the frame unreadable."""
    if row.get("label_source") != "operator":
        return False
    if row.get("operator_mark") == "unreadable":
        return row.get("xy") is None
    xy = row.get("xy")
    return isinstance(xy, list) and len(xy) == 2


def _effective_xy(row: dict, corrections: list[dict]) -> list[int] | None:
    """Latest correction for this frame, otherwise the operator label."""
    if row.get("operator_mark") == "unreadable":
        return None
    for entry in reversed(corrections):
        if entry.get("frame") == row.get("file"):
            xy = entry["new_xy"]
            return [int(xy[0]), int(xy[1])]
    xy = row.get("xy")
    if not (isinstance(xy, list) and len(xy) == 2):
        return None
    return [int(xy[0]), int(xy[1])]


def _load_corrections(session_id: str) -> list[dict]:
    path = SESSIONS / session_id / "label_corrections.json"
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path} is not a list")
    return data


def _arm(index: int) -> str | None:
    """Even frames only. Horizontal x rises; vertical y falls."""
    if index % 2:
        return None
    if 0 <= index <= 22:
        return "horizontal"
    if 24 <= index <= 42:
        return "vertical"
    return None


def _step_ok(arm: str, previous: list[int], current: list[int]) -> bool:
    """Hold or a step of 1 or 2 along the arm. A reversal or a larger step fails."""
    if arm == "horizontal":
        return current[0] - previous[0] in (0, 1, 2)
    return previous[1] - current[1] in (0, 1, 2)


def geometry_breaks(session_id: str, rows: list[dict], corrections: list[dict]) -> list[dict]:
    """Even-frame labels that reverse or jump more than 2. No reader."""
    grouped: dict[tuple[str, str], list[tuple[int, str, list[int]]]] = {}
    for row in rows:
        match = _SWEEP_FRAME.match(str(row.get("file", "")))
        if match is None:
            continue
        index = int(match.group(2))
        arm = _arm(index)
        if arm is None:
            continue
        xy = _effective_xy(row, corrections)
        if xy is None:
            continue
        grouped.setdefault((match.group(1), arm), []).append((index, str(row["file"]), xy))
    breaks: list[dict] = []
    for (sweep, arm), frames in grouped.items():
        frames.sort()
        for position, (index, name, xy) in enumerate(frames):
            if position == 0:
                continue
            previous = frames[position - 1]
            if _step_ok(arm, previous[2], xy):
                continue
            nxt = frames[position + 1] if position + 1 < len(frames) else None
            step = xy[0] - previous[2][0] if arm == "horizontal" else xy[1] - previous[2][1]
            breaks.append(
                {
                    "session": session_id,
                    "sweep": sweep,
                    "arm": arm,
                    "frame": name,
                    "xy": xy,
                    "step": step,
                    "previous": {"file": previous[1], "xy": previous[2]},
                    "next": None if nxt is None else {"file": nxt[1], "xy": nxt[2]},
                }
            )
    return breaks


def _regression_ids() -> set[str]:
    if not _REGRESSION.is_file():
        return set()
    data = json.loads(_REGRESSION.read_text(encoding="utf-8"))
    return {str(item) for item in data.get("sessions") or []}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test", nargs="+", required=True)
    parser.add_argument(
        "--geometry",
        action="store_true",
        help="List even-frame labels that break the arm step, and do not lock",
    )
    args = parser.parse_args(argv)

    if SPLIT.is_file() and not args.geometry:
        print(f"FAIL: {SPLIT} already exists; the split stays shut", flush=True)
        return 1
    labels: list[tuple[int, int]] = []
    breaks: list[dict] = []
    for session_id in args.test:
        path = SESSIONS / session_id / "labels.json"
        if not path.is_file():
            print(f"FAIL: missing {path}", flush=True)
            return 2
        rows = json.loads(path.read_text(encoding="utf-8"))
        test_rows = [row for row in rows if _in_test_set(session_id, row)]
        if any(not _reviewed(row) for row in test_rows):
            print(f"FAIL: {session_id} still has unlabeled frames", flush=True)
            return 2
        corrections = _load_corrections(session_id)
        breaks.extend(geometry_breaks(session_id, test_rows, corrections))
        if args.geometry:
            continue
        if session_id in _TRAIN:
            print(f"FAIL: {session_id} supplied templates and cannot be a test session", flush=True)
            return 2
        if session_id in _regression_ids():
            print(f"FAIL: {session_id} is regression and cannot gate a reader", flush=True)
            return 2
        for row in test_rows:
            if row.get("operator_mark") == "unreadable":
                continue
            xy = _effective_xy(row, corrections)
            if xy is None:
                continue
            labels.append((xy[0], xy[1]))
    if breaks:
        print("FAIL: arm geometry needs review before the lock:", flush=True)
        for item in breaks:
            nxt = item["next"]
            nxt_text = "none" if nxt is None else f"{nxt['file']} {nxt['xy'][0]}, {nxt['xy'][1]}"
            prev = item["previous"]
            print(
                f"  {item['session']} {item['sweep']} {item['arm']} {item['frame']} "
                f"{item['xy'][0]}, {item['xy'][1]} step {item['step']} "
                f"between {prev['file']} {prev['xy'][0]}, {prev['xy'][1]} and {nxt_text}",
                flush=True,
            )
        return 4
    if args.geometry:
        print(f"geometry ok sessions={list(args.test)}", flush=True)
        return 0
    missing = _missing(labels)
    if missing:
        print("FAIL: test set is short of the required reads:", flush=True)
        for item in missing:
            print(f"  {item}", flush=True)
        return 3
    payload = {
        "train": list(_TRAIN),
        "test": list(args.test),
        "locked_before_test_score": True,
        "notes": (
            "New gate after the first held-out set missed truncated reads. "
            "Labels come from the glyphs. Do not score more than once. "
            "Do not cut templates from the test sessions."
        ),
    }
    SESSIONS.mkdir(parents=True, exist_ok=True)
    SPLIT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"locked {SPLIT} test={list(args.test)} frames={len(labels)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
