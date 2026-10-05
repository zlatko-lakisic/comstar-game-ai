"""Score the locked v2 cursorstat test sessions once.

Does not open split.json or gate_report.json from the first gate.
If the v2 split is missing, or a frame is unlabeled, this exits
without writing a report.

A frame marked unreadable is not a miss. When the reader still returns
a coordinate, that frame is listed on its own and is not a wrong read.

A wrong read is not counted until its crop has been written. The first
pass prints those crop paths and does not write gate_report_v2.json.
Fix the label and run again, or pass --seal after the label is right.

A label fix is a row in label_corrections.json. labels.json is not
edited. The row is refused unless that frame is on the current
wrong-read list. The sealed report lists every correction and keeps
the corrected count apart from the wrong count.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

SESSIONS = ROOT / "data" / "runtime" / "cursorstat_sessions"
SPLIT = SESSIONS / "split_v2.json"
REPORT = SESSIONS / "gate_report_v2.json"

# Same box as scripts/label_cursorstat_gate.py. PIL's bottom is exclusive.
_CROP = (20, 80, 780, 151)
_SCALE = 3


def _reviewed(item: dict) -> bool:
    if item.get("label_source") != "operator":
        return False
    if item.get("operator_mark") == "unreadable":
        return item.get("xy") is None
    xy = item.get("xy")
    return isinstance(xy, list) and len(xy) == 2


class CorrectionRefused(Exception):
    """The frame is not on the current wrong-read list."""

    def __init__(self, frame: str) -> None:
        self.frame = frame
        super().__init__(frame)


def load_corrections(session: Path) -> list[dict]:
    path = session / "label_corrections.json"
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path} is not a list")
    return data


def effective_xy(item: dict, corrections: list[dict]) -> list[int]:
    """The latest correction for this frame, otherwise the operator label."""
    frame = item["file"]
    for entry in reversed(corrections):
        if entry.get("frame") == frame:
            xy = entry["new_xy"]
            return [int(xy[0]), int(xy[1])]
    xy = item["xy"]
    return [int(xy[0]), int(xy[1])]


def record_correction(
    session: Path,
    frame: str,
    new_xy: tuple[int, int],
    reason: str,
    wrong_frames: set[str],
    *,
    timestamp: str,
) -> dict:
    """Append one correction. Does not open labels.json for writing."""
    if frame not in wrong_frames:
        raise CorrectionRefused(frame)
    labels_path = session / "labels.json"
    before = labels_path.read_bytes()
    labels = json.loads(before.decode("utf-8"))
    row = next((item for item in labels if item.get("file") == frame), None)
    if row is None or row.get("xy") is None:
        raise CorrectionRefused(frame)
    corrections = load_corrections(session)
    entry = {
        "frame": frame,
        "old_xy": effective_xy(row, corrections),
        "new_xy": [int(new_xy[0]), int(new_xy[1])],
        "reason": reason,
        "timestamp": timestamp,
    }
    corrections.append(entry)
    (session / "label_corrections.json").write_text(
        json.dumps(corrections, indent=2) + "\n",
        encoding="utf-8",
    )
    if labels_path.read_bytes() != before:
        raise RuntimeError("labels.json was edited")
    return entry


def _save_crop(source: Path, dest: Path) -> None:
    image = Image.open(source).convert("L")
    band = ImageOps.autocontrast(image.crop(_CROP))
    band = band.resize(
        (band.width * _SCALE, band.height * _SCALE),
        Image.Resampling.NEAREST,
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    band.save(dest)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--seal",
        action="store_true",
        help="Write the one-shot report after wrong-read crops have been checked",
    )
    parser.add_argument(
        "--correct",
        nargs=4,
        metavar=("SESSION", "FRAME", "X", "Y"),
        help="Record a label correction for one frame on the current wrong-read list",
    )
    parser.add_argument("--reason", default="", help="Why the operator changed the label")
    args = parser.parse_args(argv)
    if args.correct and args.seal:
        print("FAIL: record the correction before sealing", flush=True)
        return 2
    if args.correct and not args.reason.strip():
        print("FAIL: a correction needs a reason", flush=True)
        return 2

    from comstar_game_ai.game_io.campaign.console_cursorstat import (
        read_console_cursorstat,
    )

    if REPORT.is_file():
        print(f"FAIL: {REPORT} already exists; the test split stays shut", flush=True)
        return 1
    if not SPLIT.is_file():
        print(f"FAIL: missing {SPLIT}. Gate not opened.", flush=True)
        return 2
    split = json.loads(SPLIT.read_text(encoding="utf-8"))
    test_ids = list(split.get("test") or [])
    rows = []
    listed_corrections: list[dict] = []
    for session_id in test_ids:
        session = SESSIONS / session_id
        labels_path = session / "labels.json"
        if not session.is_dir() or not labels_path.is_file():
            print(f"FAIL: test session {session_id} is not on disk. Gate not opened.", flush=True)
            return 2
        labels = json.loads(labels_path.read_text(encoding="utf-8"))
        if any(not _reviewed(item) for item in labels):
            print(f"FAIL: {session_id} still has unlabeled frames. Gate not opened.", flush=True)
            return 2
        corrections = load_corrections(session)
        for entry in corrections:
            listed_corrections.append(
                {
                    "session": session_id,
                    "frame": entry["frame"],
                    "old_xy": entry["old_xy"],
                    "new_xy": entry["new_xy"],
                    "reason": entry["reason"],
                    "timestamp": entry["timestamp"],
                }
            )
        for item in labels:
            path = session / item["file"]
            reading = read_console_cursorstat(Image.open(path))
            got = reading.xy
            marked_unreadable = item.get("operator_mark") == "unreadable"
            crop_path = None
            if marked_unreadable:
                kind = "reader_on_unreadable" if got is not None else "unreadable"
                expected = None
            else:
                expected = effective_xy(item, corrections)
                expected_xy = (expected[0], expected[1])
                if got is None:
                    kind = "miss"
                elif got == expected_xy:
                    kind = "read"
                else:
                    kind = "wrong"
                    dest = session / "review_crops" / item["file"]
                    _save_crop(path, dest)
                    crop_path = str(dest)
            rows.append(
                {
                    "session": session_id,
                    "file": item["file"],
                    "expected": expected,
                    "got": list(got) if got is not None else None,
                    "confidence": reading.confidence,
                    "reason": reading.reason,
                    "kind": kind,
                    "crop": crop_path,
                }
            )
    if args.correct:
        session_id, frame, x_text, y_text = args.correct
        if session_id not in test_ids:
            print(f"FAIL: {session_id} is not in the locked test", flush=True)
            return 2
        wrong_frames = {
            row["file"]
            for row in rows
            if row["session"] == session_id and row["kind"] == "wrong"
        }
        try:
            entry = record_correction(
                SESSIONS / session_id,
                frame,
                (int(x_text), int(y_text)),
                args.reason.strip(),
                wrong_frames,
                timestamp=_utc_now(),
            )
        except CorrectionRefused:
            print(f"FAIL: {frame} is not on the current wrong-read list", flush=True)
            return 5
        print(
            f"corrected {session_id}/{entry['frame']} {entry['old_xy']} -> {entry['new_xy']}",
            flush=True,
        )
        return 0
    total = len(rows)
    counts = {
        name: sum(1 for row in rows if row["kind"] == name)
        for name in ("read", "miss", "wrong", "unreadable", "reader_on_unreadable")
    }
    reader_on_unreadable = [row for row in rows if row["kind"] == "reader_on_unreadable"]
    wrongs = [row for row in rows if row["kind"] == "wrong"]
    print(
        f"frames={total} read={counts['read']} miss={counts['miss']} "
        f"wrong={counts['wrong']} corrected={len(listed_corrections)} "
        f"unreadable={counts['unreadable']} "
        f"reader_on_unreadable={counts['reader_on_unreadable']}",
        flush=True,
    )
    if reader_on_unreadable:
        print("reader returned a value on a frame marked unreadable:", flush=True)
        for row in reader_on_unreadable:
            print(
                f"  {row['session']}/{row['file']} got={row['got']} "
                f"confidence={row['confidence']}",
                flush=True,
            )
    if wrongs and not args.seal:
        print("wrong reads are not counted yet. Recheck each crop, then fix the label or rerun with --seal:", flush=True)
        for row in wrongs:
            print(
                f"  {row['session']}/{row['file']} expected={row['expected']} "
                f"got={row['got']} crop={row['crop']}",
                flush=True,
            )
        return 4
    report = {
        "sessions": test_ids,
        "frames": total,
        "read": counts["read"],
        "miss": counts["miss"],
        "wrong": counts["wrong"],
        "corrected": len(listed_corrections),
        "corrections": listed_corrections,
        "unreadable": counts["unreadable"],
        "reader_on_unreadable": counts["reader_on_unreadable"],
        "reader_on_unreadable_rows": [
            {
                "session": row["session"],
                "file": row["file"],
                "got": row["got"],
                "confidence": row["confidence"],
            }
            for row in reader_on_unreadable
        ],
        "rows": rows,
    }
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"report={REPORT}", flush=True)
    if wrongs:
        print("wrong reads:", flush=True)
        for row in wrongs:
            print(
                f"  {row['session']}/{row['file']} expected={row['expected']} "
                f"got={row['got']} crop={row['crop']}",
                flush=True,
            )
    return 0 if counts["wrong"] == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
