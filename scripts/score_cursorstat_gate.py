"""Score the locked v2 cursorstat test sessions once.

Does not open split.json or gate_report.json from the first gate.
If the v2 split is missing, or a frame is unlabeled, this exits
without writing a report.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

SESSIONS = ROOT / "data" / "runtime" / "cursorstat_sessions"
SPLIT = SESSIONS / "split_v2.json"
REPORT = SESSIONS / "gate_report_v2.json"


def main() -> int:
    from PIL import Image

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
    for session_id in test_ids:
        session = SESSIONS / session_id
        labels_path = session / "labels.json"
        if not session.is_dir() or not labels_path.is_file():
            print(f"FAIL: test session {session_id} is not on disk. Gate not opened.", flush=True)
            return 2
        labels = json.loads(labels_path.read_text(encoding="utf-8"))
        if any(item.get("xy") is None for item in labels):
            print(f"FAIL: {session_id} still has unlabeled frames. Gate not opened.", flush=True)
            return 2
        for item in labels:
            path = session / item["file"]
            expected = (int(item["xy"][0]), int(item["xy"][1]))
            reading = read_console_cursorstat(Image.open(path))
            got = reading.xy
            if got is None:
                kind = "miss"
            elif got == expected:
                kind = "read"
            else:
                kind = "wrong"
            rows.append(
                {
                    "session": session_id,
                    "file": item["file"],
                    "expected": list(expected),
                    "got": list(got) if got is not None else None,
                    "confidence": reading.confidence,
                    "reason": reading.reason,
                    "kind": kind,
                }
            )
    total = len(rows)
    counts = {name: sum(1 for row in rows if row["kind"] == name) for name in ("read", "miss", "wrong")}
    report = {
        "sessions": test_ids,
        "frames": total,
        "read": counts["read"],
        "miss": counts["miss"],
        "wrong": counts["wrong"],
        "rows": rows,
    }
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        f"frames={total} read={counts['read']} miss={counts['miss']} "
        f"wrong={counts['wrong']} report={REPORT}",
        flush=True,
    )
    return 0 if counts["wrong"] == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
