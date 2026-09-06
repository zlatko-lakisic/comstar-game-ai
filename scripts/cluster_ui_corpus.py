"""Cluster the captured frame corpus and match each cluster against the UI atlas.

Phase 4 has to drive the unresolved-frame corpus to zero unknowns. Doing that by
eye does not scale past a few hundred frames, and it hides the useful structure:
454 frames are not 454 problems, they are a handful of panels photographed
repeatedly. This groups frames by measured signature, names each group from the
atlas, and lists what is left over — the leftovers are the actual work.

Analysis is cached to JSON because a full pass costs about two minutes, and the
interesting part is re-reading the result with different questions.

    python scripts/cluster_ui_corpus.py            # analyse (or reuse cache)
    python scripts/cluster_ui_corpus.py --refresh  # re-analyse from the frames
"""

from __future__ import annotations

import argparse
import glob
import json
import os
from pathlib import Path

CACHE = Path("data/runtime/ui_corpus_signatures.json")
FRAMES = "data/runtime/modal-unresolved-*-raw.png"


def analyse(paths: list[str]) -> list[dict]:
    from PIL import Image

    from comstar_game_ai.game_io.campaign.modal import (
        blocking_ui_present,
        localize_panel_close_x,
        panel_bounds,
    )
    from comstar_game_ai.game_io.campaign.ui_mode import classify_campaign_image

    rows: list[dict] = []
    for index, path in enumerate(paths, start=1):
        record: dict = {"path": os.path.basename(path)}
        try:
            image = Image.open(path)
            record["size"] = list(image.size)
            rgb = image.convert("RGB")
            bounds = panel_bounds(rgb)
            close = localize_panel_close_x(rgb)
            width, height = image.size
            record["mode"] = classify_campaign_image(rgb).mode.value
            record["blocking"] = bool(blocking_ui_present(rgb))
            record["panel"] = (
                None
                if bounds is None
                else [
                    round(bounds[0] / width, 3),
                    round(bounds[1] / width, 3),
                    round(bounds[2] / height, 3),
                ]
            )
            record["close_x"] = (
                None if close is None else [round(close.x_norm, 3), round(close.y_norm, 3)]
            )
        except Exception as exc:  # one bad frame must not cost the whole pass
            record["error"] = f"{type(exc).__name__}: {exc}"
        rows.append(record)
        if index % 50 == 0:
            print(f"  ...{index}/{len(paths)}", flush=True)
    return rows


def signature(row: dict) -> tuple:
    if "error" in row:
        return ("error", row["error"][:40])
    if row.get("size") != [1920, 1080]:
        return ("odd_size", tuple(row.get("size") or ()))
    panel = row.get("panel")
    return (
        row.get("mode"),
        row.get("blocking"),
        None if panel is None else tuple(round(v, 2) for v in panel),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true", help="re-analyse the frames")
    args = parser.parse_args()

    if args.refresh or not CACHE.exists():
        paths = sorted(glob.glob(FRAMES))
        if not paths:
            print(f"no frames matched {FRAMES}")
            return 1
        print(f"analysing {len(paths)} frames (cache miss)...")
        rows = analyse(paths)
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(rows, indent=1), encoding="utf-8")
        print(f"cached -> {CACHE}")
    else:
        rows = json.loads(CACHE.read_text(encoding="utf-8"))
        print(f"reusing {CACHE} ({len(rows)} frames); --refresh to re-analyse")

    from comstar_game_ai.game_io.campaign.ui_atlas import match_geometry

    clusters: dict[tuple, list[dict]] = {}
    for row in rows:
        clusters.setdefault(signature(row), []).append(row)

    print(f"\n{len(rows)} frames -> {len(clusters)} signatures\n")
    header = f"{'n':>5}  {'mode':<13} {'block':<6} {'panel(l,r,top)':<20} {'atlas':<22} closeX"
    print(header)
    print("-" * len(header))

    identified = 0
    stale = 0
    no_panel = 0
    unknown: list[tuple[tuple, int]] = []
    for key, group in sorted(clusters.items(), key=lambda kv: -len(kv[1])):
        panel = key[2] if len(key) > 2 else None
        name = ""
        if key[0] in ("error", "odd_size"):
            # Not a UI question. These predate the client-rect capture fix: a
            # 1936x1119 frame is the window rect, so every derived coordinate in it
            # is offset and the frame cannot be scored against the atlas at all.
            name = "STALE CAPTURE"
            stale += len(group)
        elif panel is not None:
            match = match_geometry(*panel)
            name = match.entry.id if match else "UNMATCHED"
            if match:
                identified += len(group)
            else:
                unknown.append((key, len(group)))
        else:
            name = "(no panel)"
            no_panel += len(group)
        close = group[0].get("close_x")
        print(
            f"{len(group):>5}  {str(key[0]):<13} {str(key[1] if len(key) > 1 else ''):<6} "
            f"{str(panel):<20} {name:<22} {close}"
        )

    total = len(rows)
    valid = total - stale
    print(f"\n{total} frames: {stale} stale captures, {valid} scorable")
    if valid:
        print(
            f"of the {valid} scorable: {identified} identified ({identified / valid:.0%}), "
            f"{no_panel} with no panel, {sum(n for _, n in unknown)} unmatched"
        )
    if unknown:
        print(f"\n{len(unknown)} unmatched signatures — these are the Phase 4 worklist:")
        for key, count in unknown:
            print(f"  {count:>4}  {key}   e.g. {clusters[key][0]['path']}")
    else:
        print("\nno unmatched signatures: every scorable frame with a panel is named")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
