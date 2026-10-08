"""Homography recovery on a synthetic pitched camera. No live frames."""

from __future__ import annotations

import cv2
import numpy as np

from comstar_game_ai.game_io.campaign.map_homography import (
    GRID_HELD_OUT,
    HELD_OUT_LIMIT,
    affine_map_residuals,
    fit_homography,
    map_residuals,
    max_error,
)
from comstar_game_ai.game_io.campaign.map_projection import MapClientSample


def _pitched_samples() -> list[MapClientSample]:
    width, height = 1280, 720
    src = np.array([[0, 0], [width, 0], [width, height], [0, height]], dtype=np.float32)
    dst = np.array([[70, 100], [120, 96], [112, 55], [68, 60]], dtype=np.float32)
    matrix = cv2.getPerspectiveTransform(src, dst)
    samples = []
    xs = (0.14, 0.28, 0.42, 0.56, 0.70)
    ys = (0.16, 0.26, 0.36, 0.46, 0.54)
    for y in ys:
        for x in xs:
            point = np.array([[[x * width, y * height]]], dtype=np.float64)
            mapped = cv2.perspectiveTransform(point, matrix)
            samples.append(
                MapClientSample(
                    client_xy=(x, y),
                    map_xy=(float(mapped[0, 0, 0]), float(mapped[0, 0, 1])),
                )
            )
    return samples


def test_homography_held_out_is_within_three_map_units():
    samples = _pitched_samples()
    held = set(GRID_HELD_OUT)
    fit_samples = [sample for index, sample in enumerate(samples) if index not in held]
    held_samples = [sample for index, sample in enumerate(samples) if index in held]
    fitted = fit_homography(fit_samples, width=1280, height=720)
    assert fitted is not None
    errors = map_residuals(fitted.client_to_map, held_samples)
    assert max_error(errors) <= HELD_OUT_LIMIT
    assert max_error(errors) < 0.05


def test_affine_on_a_pitched_quad_is_worse_than_the_homography():
    samples = _pitched_samples()
    held = set(GRID_HELD_OUT)
    fit_samples = [sample for index, sample in enumerate(samples) if index not in held]
    held_samples = [sample for index, sample in enumerate(samples) if index in held]
    fitted = fit_homography(fit_samples, width=1280, height=720)
    assert fitted is not None
    homo = max_error(map_residuals(fitted.client_to_map, held_samples))
    affine = affine_map_residuals(fit_samples)
    assert affine is not None
    # The affine fit residual is on the fit set; compare held-out via the inverse.
    from comstar_game_ai.game_io.campaign.map_projection import calibrate_affine

    transform = calibrate_affine(fit_samples)
    assert transform is not None
    affine_held = max_error(map_residuals(transform.client_to_map, held_samples))
    assert homo < affine_held


def test_refit_drops_one_outlier_and_stays_valid():
    from comstar_game_ai.game_io.campaign.map_fit_runtime import MapFitRuntime

    clean = [
        MapClientSample(client_xy=(x, y), map_xy=(80.0 + 40.0 * x, 90.0 - 30.0 * y))
        for x in (0.2, 0.4, 0.6, 0.8)
        for y in (0.2, 0.4)
    ]
    fitted = fit_homography(clean, width=1280, height=720)
    assert fitted is not None
    runtime = MapFitRuntime(
        homography=fitted,
        tolerance=HELD_OUT_LIMIT,
        grid=((0.42, 0.36),),
        min_points=4,
        valid=True,
    )
    poisoned = list(clean)
    poisoned[0] = MapClientSample(
        client_xy=poisoned[0].client_xy,
        map_xy=(poisoned[0].map_xy[0] + 40.0, poisoned[0].map_xy[1]),
    )
    assert runtime.refit(poisoned, width=1280, height=720)
    assert runtime.valid
    assert runtime.log[-1]["decision"] == "valid"


def test_missing_report_is_invalid(tmp_path):
    from comstar_game_ai.game_io.campaign.map_fit_runtime import load_fit_runtime

    runtime = load_fit_runtime(tmp_path / "missing.json")
    assert not runtime.valid
    assert runtime.homography is None
