"""Load the step-2 homography and decide when to keep it.

Grid size, screen positions, and the one-point tolerance come from the fit
report. Until that report exists and passed its held-out gate, the fit is
invalid and a march must not run.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from comstar_game_ai.game_io.campaign.map_homography import (
    HELD_OUT_LIMIT,
    MapHomography,
    fit_homography,
    map_residuals,
    max_error,
)
from comstar_game_ai.game_io.campaign.map_projection import MapClientSample

DEFAULT_REPORT = (
    Path(__file__).resolve().parents[4]
    / "data"
    / "runtime"
    / "homography_sessions"
    / "fit_report.json"
)


@dataclass
class MapFitRuntime:
    """One stored fit plus a log of every probe and refit."""

    homography: MapHomography | None
    tolerance: float | None
    grid: tuple[tuple[float, float], ...]
    min_points: int
    valid: bool
    camera_token: str = ""
    saved_at: float | None = None
    log: list[dict[str, object]] = field(default_factory=list)
    pending_trigger: str = ""

    def note(self, trigger: str) -> None:
        """Record that the camera may have moved. The pre-march check still runs."""
        self.pending_trigger = trigger
        self.log.append({"event": "trigger", "trigger": trigger, "at": time.time()})

    def predict(self, client_xy: tuple[float, float]) -> tuple[float, float] | None:
        if self.homography is None:
            return None
        return self.homography.client_to_map(client_xy)

    def one_point(
        self,
        *,
        client_xy: tuple[float, float],
        read_xy: tuple[float, float] | None,
        trigger: str,
    ) -> str:
        """Return ``keep`` or ``refit``. A missing read is outside tolerance."""
        predicted = self.predict(client_xy)
        error = None
        if predicted is not None and read_xy is not None and self.tolerance is not None:
            error = (
                (predicted[0] - read_xy[0]) ** 2 + (predicted[1] - read_xy[1]) ** 2
            ) ** 0.5
        decision = "keep" if error is not None and error <= self.tolerance else "refit"
        self.log.append(
            {
                "event": "probe",
                "trigger": trigger,
                "pixel": [client_xy[0], client_xy[1]],
                "read": list(read_xy) if read_xy is not None else None,
                "prediction": list(predicted) if predicted is not None else None,
                "error": error,
                "decision": decision,
            }
        )
        self.pending_trigger = ""
        return decision

    def refit(
        self,
        samples: list[MapClientSample],
        *,
        width: int,
        height: int,
    ) -> bool:
        """Refit once. Drop the worst point if it alone breaks the tolerance.

        Returns whether the stored fit is valid afterwards.
        """
        if len(samples) < self.min_points:
            self.valid = False
            self.log.append(
                {
                    "event": "refit",
                    "decision": "invalid",
                    "reason": "below_min_points",
                    "count": len(samples),
                }
            )
            return False
        fitted = fit_homography(samples, width=width, height=height)
        if fitted is None:
            self.valid = False
            self.log.append({"event": "refit", "decision": "invalid", "reason": "fit_failed"})
            return False
        errors = map_residuals(fitted.client_to_map, samples)
        limit = self.tolerance if self.tolerance is not None else HELD_OUT_LIMIT
        # One point far above the others: drop it and refit once. A homography
        # can hide the bad point, so the drop is the omission that actually helps.
        if max_error(errors) > limit and len(samples) - 1 >= self.min_points:
            best_fit = None
            best_errors = errors
            best_max = max_error(errors)
            for index in range(len(samples)):
                kept = [sample for i, sample in enumerate(samples) if i != index]
                trial = fit_homography(kept, width=width, height=height)
                if trial is None:
                    continue
                trial_errors = map_residuals(trial.client_to_map, kept)
                trial_max = max_error(trial_errors)
                if trial_max < best_max:
                    best_fit = trial
                    best_errors = trial_errors
                    best_max = trial_max
            if best_fit is not None:
                fitted = best_fit
                errors = best_errors
        ok = max_error(errors) <= limit
        self.homography = fitted
        self.valid = ok
        self.saved_at = time.time()
        self.log.append(
            {
                "event": "refit",
                "decision": "valid" if ok else "invalid",
                "max_error": max_error(errors),
                "count": len(errors),
            }
        )
        return ok


def load_fit_runtime(path: Path | None = None) -> MapFitRuntime:
    """Load the fit report. Missing or failed reports are invalid."""
    report_path = path or DEFAULT_REPORT
    empty = MapFitRuntime(
        homography=None,
        tolerance=None,
        grid=(),
        min_points=4,
        valid=False,
    )
    if not report_path.is_file():
        return empty
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    recommendation = payload.get("recommendation") or {}
    matrix = recommendation.get("matrix")
    tolerance = recommendation.get("tolerance")
    grid = recommendation.get("grid") or []
    if not recommendation.get("passed") or matrix is None or tolerance is None:
        return empty
    return MapFitRuntime(
        homography=MapHomography(
            matrix=tuple(tuple(row) for row in matrix),
            width=int(recommendation.get("width") or 1280),
            height=int(recommendation.get("height") or 720),
        ),
        tolerance=float(tolerance),
        grid=tuple((float(point[0]), float(point[1])) for point in grid),
        min_points=int(recommendation.get("min_points") or 4),
        valid=True,
        camera_token=str(payload.get("zoom_notch") or ""),
        saved_at=payload.get("saved_at"),
    )
