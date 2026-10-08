"""Fit a locked homography session once. Does not refit after the report exists.

    python scripts/fit_homography_session.py zoom0 zoom1 zoom2 --publish

Held-out points are never used to choose the matrix. Subset residuals are
reported once. --publish writes the runtime fit only when every session's
held-out residual is within 3 map units.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

SESSIONS = ROOT / "data" / "runtime" / "homography_sessions"
PUBLISHED = SESSIONS / "fit_report.json"


def _samples(points: list[dict], indices: list[int]):
    from comstar_game_ai.game_io.campaign.map_projection import MapClientSample

    found = []
    for index in indices:
        point = points[index]
        if point.get("xy") is None:
            continue
        found.append(
            MapClientSample(
                client_xy=(float(point["client"][0]), float(point["client"][1])),
                map_xy=(float(point["xy"][0]), float(point["xy"][1])),
            )
        )
    return found


def _finite(values: list[float]) -> list[float]:
    return [value for value in values if math.isfinite(value)]


def _summarize(name: str, errors: list[float]) -> dict:
    from comstar_game_ai.game_io.campaign.map_homography import max_error

    finite = _finite(errors)
    return {
        "name": name,
        "count": len(errors),
        "max": max_error(errors),
        "mean": (sum(finite) / len(finite)) if finite else None,
        "per_point": errors,
    }


def fit_session(session: Path) -> dict:
    from comstar_game_ai.game_io.campaign.map_homography import (
        FIT_SUBSETS,
        HELD_OUT_LIMIT,
        affine_map_residuals,
        fit_homography,
        map_residuals,
        screen_band,
    )

    report_path = session / "fit_report.json"
    if report_path.is_file():
        return json.loads(report_path.read_text(encoding="utf-8"))
    split = json.loads((session / "split.json").read_text(encoding="utf-8"))
    if not split.get("locked_before_fit"):
        raise SystemExit(f"FAIL: {session} split was not locked before the fit")
    samples_payload = json.loads((session / "samples.json").read_text(encoding="utf-8"))
    points = list(samples_payload["points"])
    held_idx = [int(index) for index in split["held_out"]]
    fit_idx = [index for index in range(len(points)) if index not in set(held_idx)]
    width = int(samples_payload.get("width") or 1280)
    height = int(samples_payload.get("height") or 720)
    fit_samples = _samples(points, fit_idx)
    held_samples = _samples(points, held_idx)
    homography = fit_homography(fit_samples, width=width, height=height)
    if homography is None:
        raise SystemExit(f"FAIL: {session.name} homography did not fit")
    held_errors = map_residuals(homography.client_to_map, held_samples)
    fit_errors = map_residuals(homography.client_to_map, fit_samples)
    affine_errors = affine_map_residuals(fit_samples + held_samples)
    # Affine compared on the same held-out points, fit on the fit set only.
    affine_held = None
    from comstar_game_ai.game_io.campaign.map_projection import calibrate_affine

    affine = calibrate_affine(fit_samples)
    if affine is not None:
        affine_held = map_residuals(affine.client_to_map, held_samples)

    subsets = []
    for name, indices in FIT_SUBSETS.items():
        subset = _samples(points, list(indices))
        fitted = fit_homography(subset, width=width, height=height)
        if fitted is None:
            subsets.append({"name": name, "max": None})
            continue
        errors = map_residuals(fitted.client_to_map, held_samples)
        subsets.append(_summarize(name, errors) | {"points": len(subset)})

    full = _summarize("full_fit", held_errors) | {"points": len(fit_samples)}
    passing = [
        item
        for item in [full, *subsets]
        if item.get("max") is not None and item["max"] <= HELD_OUT_LIMIT
    ]
    passing.sort(key=lambda item: int(item.get("points") or 0))
    smallest = passing[0] if passing else None

    drift_report = _drift(homography, samples_payload.get("drift") or {})
    seconds = [float(value) for value in samples_payload.get("cycle_seconds") or []]
    seconds.sort()
    timing = {
        "median": seconds[len(seconds) // 2] if seconds else None,
        "worst": seconds[-1] if seconds else None,
    }
    settlements = []
    for item in samples_payload.get("settlements") or []:
        expected = item.get("expected")
        got = item.get("xy")
        distance = None
        if expected is not None and got is not None:
            distance = math.hypot(got[0] - expected[0], got[1] - expected[1])
        settlements.append(
            {
                "name": item.get("name"),
                "expected": expected,
                "xy": got,
                "distance": distance,
                "within_3": distance is not None and distance <= HELD_OUT_LIMIT,
            }
        )

    passed = full["max"] <= HELD_OUT_LIMIT
    tolerance = None
    drifts = [
        value
        for value in (drift_report.get("scroll"), drift_report.get("zoom"))
        if isinstance(value, (int, float)) and math.isfinite(value)
    ]
    if drifts and passed:
        tolerance = min(drifts) / 2.0
    recommendation = None
    if passed and smallest is not None and tolerance is not None:
        grid_name = smallest["name"]
        if grid_name == "full_fit":
            grid_indices = fit_idx
        else:
            grid_indices = list(FIT_SUBSETS[grid_name])
        recommendation = {
            "passed": True,
            "matrix": [list(row) for row in homography.matrix],
            "width": width,
            "height": height,
            "tolerance": tolerance,
            "min_points": int(smallest["points"]),
            "grid_name": grid_name,
            "grid": [points[index]["client"] for index in grid_indices if points[index].get("xy")],
        }
    report = {
        "session": session.name,
        "zoom_notch": samples_payload.get("zoom_notch"),
        "saved_at": time.time(),
        "passed": passed,
        "matrix": [list(row) for row in homography.matrix],
        "width": width,
        "height": height,
        "held_out_clients": [
            [sample.client_xy[0], sample.client_xy[1]] for sample in held_samples
        ],
        "limit": HELD_OUT_LIMIT,
        "held_out": full,
        "fit_residual_max": max(fit_errors) if fit_errors else None,
        "bands": screen_band(held_samples, held_errors),
        "affine_held_out_max": max(affine_held) if affine_held else None,
        "affine_all_max": max(affine_errors) if affine_errors else None,
        "subsets": subsets,
        "settlements": settlements,
        "drift": drift_report,
        "timing": timing,
        "recommendation": recommendation,
    }
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        f"{session.name} held_out_max={full['max']:.3f} passed={passed} "
        f"affine={report['affine_held_out_max']}",
        flush=True,
    )
    return report


def _drift(homography, drift: dict) -> dict:
    client = drift.get("client")
    if not client:
        return {}
    predicted = homography.client_to_map((float(client[0]), float(client[1])))

    def gap(read) -> float | None:
        if predicted is None or read is None:
            return None
        return math.hypot(read[0] - predicted[0], read[1] - predicted[1])

    return {
        "prediction": list(predicted) if predicted is not None else None,
        "before": gap(drift.get("before")),
        "scroll": gap(drift.get("after_scroll")),
        "zoom": gap(drift.get("after_zoom")),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sessions", nargs="+")
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args(argv)
    reports = []
    for name in args.sessions:
        reports.append(fit_session(SESSIONS / name))
    if len(reports) >= 2:
        _compare_zooms(reports)
    if not args.publish:
        return 0 if all(report["passed"] for report in reports) else 3
    if not all(report["passed"] for report in reports):
        print("FAIL: not published; a zoom missed the held-out gate", flush=True)
        return 3
    chosen = next(report for report in reports if report.get("recommendation"))
    if PUBLISHED.is_file():
        print(f"FAIL: {PUBLISHED} already exists", flush=True)
        return 1
    PUBLISHED.write_text(json.dumps(chosen, indent=2), encoding="utf-8")
    print(f"published {PUBLISHED}", flush=True)
    return 0


def _compare_zooms(reports: list[dict]) -> None:
    """Say whether two zooms can share one matrix. Not a refit."""
    from comstar_game_ai.game_io.campaign.map_homography import MapHomography

    print("zoom comparison (same held-out clients, each zoom's own matrix):", flush=True)
    for left, right in zip(reports, reports[1:]):
        if not left.get("matrix") or not right.get("matrix"):
            print(
                f"  notch {left.get('zoom_notch')} vs {right.get('zoom_notch')}: "
                "no matrix",
                flush=True,
            )
            continue
        fit_a = MapHomography(
            matrix=tuple(tuple(row) for row in left["matrix"]),
            width=int(left["width"]),
            height=int(left["height"]),
        )
        fit_b = MapHomography(
            matrix=tuple(tuple(row) for row in right["matrix"]),
            width=int(right["width"]),
            height=int(right["height"]),
        )
        gaps = []
        for client in left.get("held_out_clients") or []:
            map_a = fit_a.client_to_map((client[0], client[1]))
            map_b = fit_b.client_to_map((client[0], client[1]))
            if map_a is None or map_b is None:
                continue
            gaps.append(math.hypot(map_a[0] - map_b[0], map_a[1] - map_b[1]))
        worst = max(gaps) if gaps else None
        print(
            f"  notch {left.get('zoom_notch')} vs {right.get('zoom_notch')}: "
            f"max map gap={worst}",
            flush=True,
        )


if __name__ == "__main__":
    raise SystemExit(main())
