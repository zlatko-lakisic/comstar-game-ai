"""Perspective fit from client pixels to map coordinates.

``calibrate_affine`` is a single plane ratio plus shear. A pitched camera is a
homography. Residuals here are map units, so the two fits can be compared.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np

from comstar_game_ai.game_io.campaign.map_projection import (
    MapClientSample,
    calibrate_affine,
)

# 5×5 grid, row-major. Held out before any fit: four corners, four edge
# centres, and the middle cell. The rest is the fit set.
GRID_HELD_OUT: tuple[int, ...] = (0, 2, 4, 10, 12, 14, 20, 22, 24)

# Subsets of the fit set only. The centre cell is held out, so the 3×3 is the
# eight cells around it.
FIT_SUBSETS: dict[str, tuple[int, ...]] = {
    "four_corners": (6, 8, 16, 18),
    "two_by_three": (6, 7, 8, 16, 17, 18),
    "eight_around_centre": (6, 7, 8, 11, 13, 16, 17, 18),
}

HELD_OUT_LIMIT = 3.0


@dataclass(frozen=True)
class MapHomography:
    """Maps client pixels to map coordinates. ``matrix`` is row-major 3×3."""

    matrix: tuple[tuple[float, float, float], ...]
    width: int
    height: int

    def client_to_map(self, client_xy: tuple[float, float]) -> tuple[float, float] | None:
        src = np.array(
            [[[client_xy[0] * self.width, client_xy[1] * self.height]]],
            dtype=np.float64,
        )
        try:
            dst = cv2.perspectiveTransform(src, self._array())
        except cv2.error:
            return None
        x, y = float(dst[0, 0, 0]), float(dst[0, 0, 1])
        if not math.isfinite(x) or not math.isfinite(y):
            return None
        return (x, y)

    def map_to_client(self, map_xy: tuple[float, float]) -> tuple[float, float] | None:
        inverse = np.linalg.inv(self._array())
        src = np.array([[[map_xy[0], map_xy[1]]]], dtype=np.float64)
        try:
            dst = cv2.perspectiveTransform(src, inverse)
        except cv2.error:
            return None
        x = float(dst[0, 0, 0]) / self.width
        y = float(dst[0, 0, 1]) / self.height
        if not math.isfinite(x) or not math.isfinite(y):
            return None
        return (x, y)

    def _array(self) -> np.ndarray:
        return np.array(self.matrix, dtype=np.float64)


def fit_homography(
    samples: list[MapClientSample], *, width: int, height: int
) -> MapHomography | None:
    """Least-squares homography. None when fewer than four points or the fit fails."""
    if len(samples) < 4 or width < 1 or height < 1:
        return None
    src = np.array(
        [[s.client_xy[0] * width, s.client_xy[1] * height] for s in samples],
        dtype=np.float64,
    )
    dst = np.array([[s.map_xy[0], s.map_xy[1]] for s in samples], dtype=np.float64)
    matrix, _mask = cv2.findHomography(src, dst, 0)
    if matrix is None:
        return None
    return MapHomography(
        matrix=tuple(tuple(float(value) for value in row) for row in matrix),
        width=width,
        height=height,
    )


def map_residuals(
    predict, samples: list[MapClientSample]
) -> list[float]:
    """Euclidean map error for each sample. A missed prediction is infinite."""
    errors: list[float] = []
    for sample in samples:
        predicted = predict(sample.client_xy)
        if predicted is None:
            errors.append(math.inf)
            continue
        errors.append(
            math.hypot(predicted[0] - sample.map_xy[0], predicted[1] - sample.map_xy[1])
        )
    return errors


def affine_map_residuals(samples: list[MapClientSample]) -> list[float] | None:
    """``calibrate_affine`` error in map units, via the inverse."""
    transform = calibrate_affine(samples)
    if transform is None:
        return None
    return map_residuals(transform.client_to_map, samples)


def screen_band(samples: list[MapClientSample], errors: list[float]) -> dict[str, float | None]:
    """Mean residual for the top third of the screen and the bottom third."""
    top = [err for sample, err in zip(samples, errors) if sample.client_xy[1] <= 0.33]
    bottom = [err for sample, err in zip(samples, errors) if sample.client_xy[1] >= 0.50]
    return {
        "top_mean": (sum(top) / len(top)) if top else None,
        "bottom_mean": (sum(bottom) / len(bottom)) if bottom else None,
    }


def max_error(errors: list[float]) -> float:
    return max(errors) if errors else math.inf
