"""Automate dataset build (#2): capture frames + CV auto-label → COCO.

Usage::

    # Game running — capture then label
    python scripts/detection/automate_dataset.py --capture 60 --interval 1.5

    # Label existing raw frames only
    python scripts/detection/automate_dataset.py --skip-capture --weak-armies

    # From fixture dir (no game)
    python scripts/detection/automate_dataset.py --skip-capture --images tests/fixtures/frames/map_targets
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAPTURE = ROOT / "scripts" / "detection" / "capture_frames.py"
AUTO_LABEL = ROOT / "scripts" / "detection" / "auto_label_from_cv.py"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=int, default=40, help="Frames to grab (0 = skip)")
    parser.add_argument("--skip-capture", action="store_true")
    parser.add_argument("--interval", type=float, default=1.5)
    parser.add_argument(
        "--images",
        type=Path,
        default=ROOT / "data" / "detection" / "raw",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "data" / "detection" / "coco",
    )
    parser.add_argument("--val-frac", type=float, default=0.15)
    parser.add_argument("--weak-armies", action="store_true")
    parser.add_argument("--min-boxes", type=int, default=1)
    parser.add_argument(
        "--no-auto-move",
        action="store_true",
        help="Do not pan/zoom between captures (you move the camera)",
    )
    parser.add_argument(
        "--countdown",
        type=int,
        default=0,
        help="Seconds before first capture (aim at settlements)",
    )
    parser.add_argument(
        "--pan-only",
        action="store_true",
        help="Auto-move with pans only (no zoom) for close settlement passes",
    )
    parser.add_argument(
        "--oversample-settlements",
        type=int,
        default=8,
    )
    args = parser.parse_args()

    if not args.skip_capture and args.capture > 0:
        cmd = [
            sys.executable,
            str(CAPTURE),
            "--count",
            str(args.capture),
            "--interval",
            str(args.interval),
            "--out",
            str(args.images),
            "--countdown",
            str(args.countdown),
        ]
        if not args.no_auto_move:
            cmd.append("--auto-move")
        if args.pan_only:
            cmd.append("--pan-only")
        print("+", " ".join(cmd), flush=True)
        rc = subprocess.call(cmd)
        if rc != 0:
            return rc

    label_cmd = [
        sys.executable,
        str(AUTO_LABEL),
        "--images",
        str(args.images),
        "--out",
        str(args.out),
        "--val-frac",
        str(args.val_frac),
        "--min-boxes",
        str(args.min_boxes),
        "--oversample-settlements",
        str(args.oversample_settlements),
    ]
    if args.weak_armies:
        label_cmd.append("--weak-armies")
    print("+", " ".join(label_cmd), flush=True)
    return subprocess.call(label_cmd)


if __name__ == "__main__":
    raise SystemExit(main())
