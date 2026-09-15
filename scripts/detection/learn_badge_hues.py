"""Learn settlement-badge HSV bands from KB legend colours + live Rome.

1. Reads ``FACTION_LEGEND_COLOURS`` (campaign UI atlas / settlements.py).
2. Focuses Rome via Home (capital_zoom), grabs a frame.
3. Samples rim HSV on CV badge hits (and candidate circular blobs).
4. Prints recommended ``BANDS`` and writes a debug annotated JPEG.

Usage::

    python scripts/detection/learn_badge_hues.py --countdown 10
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

# Saturated legend entries only — whites/taupe/olive fill cause terrain FPs
# (see settlements.FACTION_LEGEND_COLOURS notes / campaign_ui_atlas).
_LEGEND_TO_BAND = {
    "The House of Julii": "red",
    "The House of Brutii": "green",
    "Gaul": "green",
    "The House of Scipii": "blue",
    "S.P.Q.R.": "purple",
    "Egypt": "yellow",
}


def _rgb_to_hsv(rgb: tuple[int, int, int]) -> tuple[int, int, int]:
    bgr = np.uint8([[list(reversed(rgb))]])
    h, s, v = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)[0, 0]
    return int(h), int(s), int(v)


def _hue_window(h: int, half: int = 10) -> list[tuple[int, int]]:
    """OpenCV hue is circular 0..179; darker/lighter share hue, widen ±half."""
    lo, hi = h - half, h + half
    if lo < 0:
        return [(0, hi), (180 + lo, 179)]
    if hi > 179:
        return [(lo, 179), (0, hi - 180)]
    return [(lo, hi)]


def bands_from_legend() -> dict[str, list[tuple[int, int]]]:
    from comstar_game_ai.game_io.campaign.settlements import FACTION_LEGEND_COLOURS

    acc: dict[str, list[tuple[int, int]]] = defaultdict(list)
    print("KB legend -> HSV (saturated only):", flush=True)
    for name, band in _LEGEND_TO_BAND.items():
        rgb = FACTION_LEGEND_COLOURS[name]
        h, s, v = _rgb_to_hsv(rgb)
        wins = _hue_window(h, half=12)
        print(f"  {name}: RGB{rgb} -> H={h} S={s} V={v} band={band} wins={wins}", flush=True)
        if s < 80:
            print(f"    skip low-sat legend swatch S={s}", flush=True)
            continue
        acc[band].extend(wins)
    # Merge overlapping windows per band
    out: dict[str, list[tuple[int, int]]] = {}
    for band, wins in acc.items():
        wins = sorted(set(wins))
        merged: list[tuple[int, int]] = []
        for lo, hi in wins:
            if not merged or lo > merged[-1][1] + 1:
                merged.append((lo, hi))
            else:
                merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
        out[band] = merged
    # Keep red tight in the proposal — wider red floods terrain (see detector CAL).
    if "red" in out:
        out["red"] = [(0, 8), (168, 179)]
    return out


def _sample_rim_hsv(bgr: np.ndarray, cx: float, cy: float, r: float) -> tuple[float, float, float]:
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    th = np.linspace(0, 2 * np.pi, 48, endpoint=False)
    xs = np.clip((cx + r * 0.85 * np.cos(th)).astype(int), 0, bgr.shape[1] - 1)
    ys = np.clip((cy + r * 0.85 * np.sin(th)).astype(int), 0, bgr.shape[0] - 1)
    samples = hsv[ys, xs]
    # Prefer saturated rim pixels
    sat = samples[:, 1] >= 80
    if sat.any():
        samples = samples[sat]
    return float(np.median(samples[:, 0])), float(np.median(samples[:, 1])), float(
        np.median(samples[:, 2])
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--countdown", type=int, default=8)
    parser.add_argument("--fixture", type=Path, default=None)
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "data" / "runtime" / "detection_eval" / "hue_learn",
    )
    args = parser.parse_args()

    legend_bands = bands_from_legend()
    print("Proposed BANDS from KB:", json.dumps({k: v for k, v in legend_bands.items()}), flush=True)

    if args.fixture is not None:
        bgr = cv2.imread(str(args.fixture))
        if bgr is None:
            print(f"FAIL: cannot read {args.fixture}", flush=True)
            return 2
    else:
        from comstar_game_ai.game_io.campaign.ui_mode import grab_rgb_image
        from comstar_game_ai.game_io.input.send_input import SendInputController
        from comstar_game_ai.game_io.window import find_game_window
        from comstar_game_ai.shared.config import load_config
        from PIL import Image

        cfg = load_config()
        subs = cfg.get("game", {}).get("window_title_substrings") or ["Rome"]
        game = find_game_window(subs)
        if game is None:
            print("FAIL: Rome window not found", flush=True)
            return 2
        ctrl = SendInputController()
        ctrl.focus_window(game.hwnd)
        time.sleep(0.3)
        print("capital_zoom (Home) -> Rome...", flush=True)
        ctrl.tap_key("home", dwell_ms=50, hwnd=game.hwnd)
        time.sleep(1.2)
        # Ease out a bit so neighbouring towns' badges are readable.
        for _ in range(4):
            ctrl.tap_key("x", dwell_ms=40, hwnd=game.hwnd)
            time.sleep(0.05)
        time.sleep(0.6)
        if args.countdown > 0:
            print(
                f"\n>>> ROME FRAMED — settle camera {args.countdown}s (optional nudge) <<<\n",
                flush=True,
            )
            for i in range(args.countdown, 0, -1):
                print(f"  {i}...", flush=True)
                time.sleep(1)
        frame = grab_rgb_image(game.hwnd)
        if frame is None:
            print("FAIL: no frame", flush=True)
            return 2
        bgr = cv2.cvtColor(np.array(frame.convert("RGB")), cv2.COLOR_RGB2BGR)
        args.out.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        raw_path = args.out / f"{stamp}_rome.jpg"
        Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)).save(raw_path, quality=92)
        print(f"wrote {raw_path}", flush=True)

    # Temporarily install legend bands and detect
    import comstar_game_ai.game_io.campaign.settlement_detector as sd

    old = dict(sd.BANDS)
    sd.BANDS = legend_bands
    try:
        hits = sd.detect_settlements(bgr)
    finally:
        sd.BANDS = old

    print(f"hits with KB bands: {len(hits)}", flush=True)
    rim_by_band: dict[str, list[tuple[float, float, float]]] = defaultdict(list)
    ann = bgr.copy()
    for h in hits:
        cx, cy = h["badge_px"]
        d = float(h["badge_d"])
        hh, ss, vv = _sample_rim_hsv(bgr, cx, cy, d / 2.0)
        band = h["faction_colour"]
        rim_by_band[band].append((hh, ss, vv))
        print(
            f"  {band} @({cx},{cy}) d={d:.0f} rim_HSV=({hh:.0f},{ss:.0f},{vv:.0f})",
            flush=True,
        )
        cv2.circle(ann, (cx, cy), int(d / 2), (0, 255, 0), 2)
        cv2.putText(
            ann,
            f"{band}",
            (cx + 8, cy - 8),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (0, 255, 0),
            1,
            cv2.LINE_AA,
        )

    # Refine windows from live rim medians (darker/lighter → keep hue ±12)
    refined: dict[str, list[tuple[int, int]]] = {}
    for band, samples in rim_by_band.items():
        hs = [s[0] for s in samples]
        med = int(round(float(np.median(hs))))
        refined[band] = _hue_window(med, half=12)
        print(f"live refine {band}: median_H={med} -> {refined[band]}", flush=True)

    # Keep KB bands that had no hits yet (e.g. purple/yellow not in frame)
    final = dict(legend_bands)
    for band, wins in refined.items():
        final[band] = wins

    print("FINAL BANDS:", flush=True)
    print(repr(final), flush=True)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "learned_bands.json").write_text(
        json.dumps(
            {
                "legend_bands": {k: [list(t) for t in v] for k, v in legend_bands.items()},
                "live_refined": {k: [list(t) for t in v] for k, v in refined.items()},
                "final": {k: [list(t) for t in v] for k, v in final.items()},
                "hit_count": len(hits),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    ann_path = args.out / "rome_hits.jpg"
    cv2.imwrite(str(ann_path), ann)
    print(f"wrote {ann_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
