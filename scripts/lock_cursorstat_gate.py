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
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SESSIONS = ROOT / "data" / "runtime" / "cursorstat_sessions"
SPLIT = SESSIONS / "split_v2.json"

# 20261003-pass supplied every template except 4. The 4 was cut from
# 20261003-digits3. Neither session is a test session.
_TRAIN = ("20261003-pass", "20261003-digits3")
_ADJACENT = (100, 84, 141, 44)


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test", nargs="+", required=True)
    args = parser.parse_args(argv)

    if SPLIT.is_file():
        print(f"FAIL: {SPLIT} already exists; the split stays shut", flush=True)
        return 1
    labels: list[tuple[int, int]] = []
    for session_id in args.test:
        path = SESSIONS / session_id / "labels.json"
        if not path.is_file():
            print(f"FAIL: missing {path}", flush=True)
            return 2
        rows = json.loads(path.read_text(encoding="utf-8"))
        if any(row.get("xy") is None for row in rows):
            print(f"FAIL: {session_id} still has unlabeled frames", flush=True)
            return 2
        if session_id in _TRAIN:
            print(f"FAIL: {session_id} supplied templates and cannot be a test session", flush=True)
            return 2
        for row in rows:
            labels.append((int(row["xy"][0]), int(row["xy"][1])))
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
