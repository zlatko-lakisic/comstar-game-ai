"""Map↔client projection for the campaign camera pose.

Belief coordinates live in Rome map space. Mouse clicks use client-normalised
window coordinates for the *current* camera. This module fits an affine
transform from calibration samples (typically ``show_cursorstat`` at known
client points) and projects settlement map coords into clickable client norms.

Also maps belief coords onto the strategic radar (world-fixed), used to jump
the camera toward a target before fine calibration.

When ``show_cursorstat`` is not machine-readable (Remastered spike: console
pane only), fall back to radar-frustum AABB or an army-anchor local transform.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

from comstar_game_ai.game_io.campaign.screen_regions import BY_ID as REGION_BY_ID

_LOGGER = logging.getLogger(__name__)

#: Julii Italy campaign map extents measured against radar corners / start-position
#: coords. Coarse; good enough for radar framing, not for pixel clicks.
#: Map X increases east; map Y increases north (Rome convention).
DEFAULT_MAP_BOUNDS: tuple[float, float, float, float] = (
    0.0,  # min_x
    0.0,  # min_y
    200.0,  # max_x — Remastered campaign plane is wider than classic Italy
    150.0,  # max_y
)

#: Client norms that must contain a projected destination click.
#: Bottom capped above the selected-army parchment (y≈0.62+ eats map clicks).
#: Right capped left of the radar / end-turn column.
DEFAULT_VIEWPORT_BOUNDS: tuple[float, float, float, float] = (0.08, 0.10, 0.82, 0.58)

#: Client-norms per map unit at the **canonical** camera pose (north-up).
#: Z7 2026-09-11 @ 1280×720, N=14: viewport_w 0.74 / aabb_w 55.6 after a
#: landed Flavius march (Arretium west). Overlay-pose 0.0092 remains void.
DEFAULT_ANCHOR_SCALE: float | None = 0.0133

#: Along-bearing blend factors for near-target clicks (1.0 = full belief offset).
#: Prefer slight undershoot first — overshoot west of Segesta hits water.
NEAR_PROJECTION_BLENDS: tuple[float, ...] = (0.75, 0.85, 0.95, 1.0, 1.08)


@dataclass(frozen=True)
class MapClientSample:
    """One calibration pair: client norm ↔ map xy under a fixed camera pose."""

    client_xy: tuple[float, float]
    map_xy: tuple[float, float]


@dataclass(frozen=True)
class MapClientTransform:
    """2×3 affine: client = A @ map_homogeneous.

    ``matrix`` rows are ``[[a, b, c], [d, e, f]]`` so
    ``x_c = a*x_m + b*y_m + c``, ``y_c = d*x_m + e*y_m + f``.
    """

    matrix: tuple[tuple[float, float, float], tuple[float, float, float]]
    sample_count: int = 0
    residual_rms: float = 0.0

    def map_to_client(self, map_xy: tuple[float, float]) -> tuple[float, float]:
        x_m, y_m = float(map_xy[0]), float(map_xy[1])
        (a, b, c), (d, e, f) = self.matrix
        return (a * x_m + b * y_m + c, d * x_m + e * y_m + f)

    def client_to_map(self, client_xy: tuple[float, float]) -> tuple[float, float] | None:
        """Invert the affine when well-conditioned; None if singular."""
        (a, b, c), (d, e, f) = self.matrix
        det = a * e - b * d
        if abs(det) < 1e-12:
            return None
        x_c, y_c = float(client_xy[0]), float(client_xy[1])
        rx, ry = x_c - c, y_c - f
        x_m = (e * rx - b * ry) / det
        y_m = (-d * rx + a * ry) / det
        return (x_m, y_m)


def calibrate_affine(samples: list[MapClientSample]) -> MapClientTransform | None:
    """Least-squares affine fit from ≥3 samples. None if underdetermined/singular."""
    if len(samples) < 3:
        return None

    n = len(samples)
    ata = [[0.0] * 3 for _ in range(3)]
    atbx = [0.0, 0.0, 0.0]
    atby = [0.0, 0.0, 0.0]
    for s in samples:
        x_m, y_m = s.map_xy
        row = (float(x_m), float(y_m), 1.0)
        x_c, y_c = float(s.client_xy[0]), float(s.client_xy[1])
        for i in range(3):
            atbx[i] += row[i] * x_c
            atby[i] += row[i] * y_c
            for j in range(3):
                ata[i][j] += row[i] * row[j]

    row_x = _solve3(ata, atbx)
    row_y = _solve3(ata, atby)
    if row_x is None or row_y is None:
        return None
    transform = MapClientTransform(matrix=(row_x, row_y), sample_count=n)
    residual = fit_residual_rms(transform, samples)
    return MapClientTransform(
        matrix=transform.matrix,
        sample_count=n,
        residual_rms=residual,
    )


def fit_residual_rms(
    transform: MapClientTransform, samples: list[MapClientSample]
) -> float:
    """RMS error in client-norm space (map→client vs sample client)."""
    if not samples:
        return 0.0
    acc = 0.0
    for s in samples:
        px, py = transform.map_to_client(s.map_xy)
        dx = px - s.client_xy[0]
        dy = py - s.client_xy[1]
        acc += dx * dx + dy * dy
    return math.sqrt(acc / len(samples))


def map_to_client(
    transform: MapClientTransform,
    map_xy: tuple[float, float],
    *,
    viewport: tuple[float, float, float, float] = DEFAULT_VIEWPORT_BOUNDS,
) -> tuple[float, float] | None:
    """Project map coords; None when outside the safe map viewport."""
    x, y = transform.map_to_client(map_xy)
    x0, y0, x1, y1 = viewport
    if not (x0 <= x <= x1 and y0 <= y <= y1):
        return None
    return (x, y)


def transform_from_view_aabb(
    *,
    map_min: tuple[float, float],
    map_max: tuple[float, float],
    client_bounds: tuple[float, float, float, float] = DEFAULT_VIEWPORT_BOUNDS,
) -> MapClientTransform | None:
    """Build an axis-aligned affine from a map AABB (e.g. radar frustum) to the viewport.

    Assumes north-up camera. Map Y north maps to smaller client Y.
    """
    min_x, min_y = float(map_min[0]), float(map_min[1])
    max_x, max_y = float(map_max[0]), float(map_max[1])
    if max_x - min_x < 1e-3 or max_y - min_y < 1e-3:
        return None
    x0, y0, x1, y1 = client_bounds
    a = (x1 - x0) / (max_x - min_x)
    c = x0 - a * min_x
    e = (y0 - y1) / (max_y - min_y)
    f = y1 - e * min_y
    return MapClientTransform(matrix=((a, 0.0, c), (0.0, e, f)), sample_count=4)


def transform_from_army_anchor(
    *,
    army_map_xy: tuple[float, float],
    client_anchor: tuple[float, float] = (0.50, 0.48),
    scale: float,
    map_y_to_screen_sign: float = -1.0,
) -> MapClientTransform:
    """Local north-up transform after Lists-locate framed ``army_map_xy`` at centre.

    Used when ``show_cursorstat`` is not logged. ``scale`` is client-norms per map unit
    at the canonical pose (required — no void default).
    """
    ax, ay = float(army_map_xy[0]), float(army_map_xy[1])
    cx, cy = float(client_anchor[0]), float(client_anchor[1])
    s = float(scale)
    sign = float(map_y_to_screen_sign)
    return MapClientTransform(
        matrix=((s, 0.0, cx - s * ax), (0.0, s * sign, cy - s * sign * ay)),
        sample_count=1,
    )


def belief_to_radar_norm(
    map_xy: tuple[float, float],
    *,
    map_bounds: tuple[float, float, float, float] = DEFAULT_MAP_BOUNDS,
    radar_bounds: tuple[float, float, float, float] | None = None,
) -> tuple[float, float]:
    """Map belief coords onto the radar widget (client norms).

    Radar Y is top→bottom on screen while map Y is south→north, so Y is flipped.
    """
    if radar_bounds is None:
        radar = REGION_BY_ID.get("radar")
        if radar is None:
            radar_bounds = (0.879, 0.055, 0.998, 0.185)
        else:
            radar_bounds = radar.bounds
    min_x, min_y, max_x, max_y = map_bounds
    rx0, ry0, rx1, ry1 = radar_bounds
    mx, my = float(map_xy[0]), float(map_xy[1])
    tx = (mx - min_x) / max(max_x - min_x, 1e-6)
    ty = (my - min_y) / max(max_y - min_y, 1e-6)
    tx = min(1.0, max(0.0, tx))
    ty = min(1.0, max(0.0, ty))
    return (rx0 + tx * (rx1 - rx0), ry1 - ty * (ry1 - ry0))


def radar_norm_to_map(
    radar_xy: tuple[float, float],
    *,
    map_bounds: tuple[float, float, float, float] = DEFAULT_MAP_BOUNDS,
    radar_bounds: tuple[float, float, float, float] | None = None,
) -> tuple[float, float]:
    """Inverse of :func:`belief_to_radar_norm`."""
    if radar_bounds is None:
        radar = REGION_BY_ID.get("radar")
        radar_bounds = radar.bounds if radar is not None else (0.879, 0.055, 0.998, 0.185)
    min_x, min_y, max_x, max_y = map_bounds
    rx0, ry0, rx1, ry1 = radar_bounds
    rx, ry = float(radar_xy[0]), float(radar_xy[1])
    tx = (rx - rx0) / max(rx1 - rx0, 1e-6)
    ty = (ry1 - ry) / max(ry1 - ry0, 1e-6)
    tx = min(1.0, max(0.0, tx))
    ty = min(1.0, max(0.0, ty))
    return (min_x + tx * (max_x - min_x), min_y + ty * (max_y - min_y))


def detect_radar_frustum_map_aabb(
    image: object,
    *,
    map_bounds: tuple[float, float, float, float] = DEFAULT_MAP_BOUNDS,
    radar_bounds: tuple[float, float, float, float] | None = None,
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """Estimate the camera view AABB in map space from the red radar frustum.

    Returns ``(map_min, map_max)`` or None when the frustum is not found.
    """
    import numpy as np

    if radar_bounds is None:
        radar = REGION_BY_ID.get("radar")
        radar_bounds = radar.bounds if radar is not None else (0.879, 0.055, 0.998, 0.185)

    rgb = np.asarray(image.convert("RGB"))  # type: ignore[union-attr]
    h, w = rgb.shape[:2]
    rx0, ry0, rx1, ry1 = radar_bounds
    x0, x1 = int(w * rx0), int(w * rx1)
    y0, y1 = int(h * ry0), int(h * ry1)
    crop = rgb[y0:y1, x0:x1]
    if crop.size == 0:
        return None
    r = crop[:, :, 0].astype(np.int16)
    g = crop[:, :, 1].astype(np.int16)
    b = crop[:, :, 2].astype(np.int16)
    red = (r >= 160) & (g <= 90) & (b <= 90) & (r >= g + 40) & (r >= b + 40)
    ys, xs = np.where(red)
    if len(xs) < 8:
        return None
    ch, cw = crop.shape[:2]
    left = rx0 + (float(xs.min()) / max(cw - 1, 1)) * (rx1 - rx0)
    right = rx0 + (float(xs.max()) / max(cw - 1, 1)) * (rx1 - rx0)
    top = ry0 + (float(ys.min()) / max(ch - 1, 1)) * (ry1 - ry0)
    bottom = ry0 + (float(ys.max()) / max(ch - 1, 1)) * (ry1 - ry0)
    corners = (
        radar_norm_to_map((left, top), map_bounds=map_bounds, radar_bounds=radar_bounds),
        radar_norm_to_map((right, top), map_bounds=map_bounds, radar_bounds=radar_bounds),
        radar_norm_to_map((left, bottom), map_bounds=map_bounds, radar_bounds=radar_bounds),
        radar_norm_to_map((right, bottom), map_bounds=map_bounds, radar_bounds=radar_bounds),
    )
    xs_m = [c[0] for c in corners]
    ys_m = [c[1] for c in corners]
    return ((min(xs_m), min(ys_m)), (max(xs_m), max(ys_m)))


def map_point_near_client(
    transform: MapClientTransform,
    map_xy: tuple[float, float],
    *,
    target_client: tuple[float, float] = (0.50, 0.48),
    max_dist: float = 0.12,
) -> bool:
    """Whether ``map_xy`` projects near ``target_client`` (army-at-centre check)."""
    x, y = transform.map_to_client(map_xy)
    return math.hypot(x - target_client[0], y - target_client[1]) <= max_dist


def _solve3(
    a: list[list[float]], b: list[float]
) -> tuple[float, float, float] | None:
    """Solve 3×3 linear system with Gaussian elimination. None if singular."""
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(3):
        pivot = col
        for r in range(col + 1, 3):
            if abs(m[r][col]) > abs(m[pivot][col]):
                pivot = r
        if abs(m[pivot][col]) < 1e-12:
            return None
        m[col], m[pivot] = m[pivot], m[col]
        div = m[col][col]
        for j in range(col, 4):
            m[col][j] /= div
        for r in range(3):
            if r == col:
                continue
            factor = m[r][col]
            for j in range(col, 4):
                m[r][j] -= factor * m[col][j]
    return (m[0][3], m[1][3], m[2][3])
