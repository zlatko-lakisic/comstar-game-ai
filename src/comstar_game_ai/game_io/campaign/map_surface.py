"""Z3: detect campaign Map Overlay vs 3D map.

Separate from pose AABB verification. The radar frustum still exists on the
overlay, so zoom extent cannot see this failure mode.

Primary signal (Remastered): left/right legend panels light up with parchment
when Map Overlay is open. Interior texture alone is unreliable because the
political fill is translucent over terrain.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

_LOGGER = logging.getLogger(__name__)

#: Map-interior sample (secondary). Clear of HUD / radar / army parchment.
DEFAULT_MAP_INTERIOR_NORMS: tuple[float, float, float, float] = (0.30, 0.20, 0.70, 0.48)

#: Settlements legend (left) and factions legend (right) when overlay is up.
#: Measured 2026-09-11 on 1280×720: warm fraction ~0.03 on 3D map, ~0.27 on overlay.
LEFT_LEGEND_NORMS: tuple[float, float, float, float] = (0.01, 0.12, 0.16, 0.55)
RIGHT_LEGEND_NORMS: tuple[float, float, float, float] = (0.84, 0.20, 0.99, 0.70)

#: Warm parchment / legend chrome: bright enough, not neon-saturated.
DEFAULT_LEGEND_WARM_MIN = 0.12

#: Secondary interior heuristics (kept for logging; not primary).
DEFAULT_OVERLAY_VARIANCE_MAX = 0.0025
DEFAULT_OVERLAY_SATURATION_MIN = 0.38
DEFAULT_OVERLAY_EDGE_DENSITY_MAX = 0.045
DEFAULT_MIN_MEAN_LUMA = 0.12


@dataclass(frozen=True)
class MapSurfaceStats:
    """Raw discriminators for the sampled regions."""

    variance: float
    saturation_mean: float
    hue_bins_used: int
    edge_density: float
    mean_luma: float
    legend_warm_left: float
    legend_warm_right: float
    sample_pixels: int
    roi_norms: tuple[float, float, float, float]

    def as_log_dict(self) -> dict[str, Any]:
        return {
            "variance": round(self.variance, 6),
            "saturation_mean": round(self.saturation_mean, 4),
            "hue_bins_used": self.hue_bins_used,
            "edge_density": round(self.edge_density, 4),
            "mean_luma": round(self.mean_luma, 4),
            "legend_warm_left": round(self.legend_warm_left, 4),
            "legend_warm_right": round(self.legend_warm_right, 4),
            "sample_pixels": self.sample_pixels,
            "roi_norms": list(self.roi_norms),
        }


@dataclass(frozen=True)
class MapSurfaceCheck:
    """Surface gate result — not a pose check."""

    is_map_overlay: bool
    stats: MapSurfaceStats
    detail: str = ""

    def as_log_dict(self) -> dict[str, Any]:
        out = self.stats.as_log_dict()
        out["is_map_overlay"] = self.is_map_overlay
        out["detail"] = self.detail
        return out


def _roi_box(width: int, height: int, norms: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
    l, t, r, b = norms
    x0 = max(0, min(width - 1, int(round(l * width))))
    y0 = max(0, min(height - 1, int(round(t * height))))
    x1 = max(x0 + 1, min(width, int(round(r * width))))
    y1 = max(y0 + 1, min(height, int(round(b * height))))
    return x0, y0, x1, y1


def _hsv_pixels(crop) -> list[tuple[int, int, int]]:
    hsv = crop.convert("HSV")
    get_data = getattr(hsv, "get_flattened_data", None)
    raw = list(get_data()) if callable(get_data) else list(hsv.getdata())
    if raw and isinstance(raw[0], tuple):
        return [(int(a), int(b), int(c)) for a, b, c in raw]
    return [tuple(int(x) for x in raw[i : i + 3]) for i in range(0, len(raw), 3)]  # type: ignore[misc]


def _legend_warm_fraction(rgb, norms: tuple[float, float, float, float]) -> float:
    """Fraction of legend ROI that looks like lit parchment / legend chrome."""
    w, h = rgb.size
    crop = rgb.crop(_roi_box(w, h, norms))
    pixels = _hsv_pixels(crop)
    if not pixels:
        return 0.0
    warm = 0
    for _h, s, v in pixels:
        # Parchment panels: fairly bright, moderate saturation (not neon fills).
        if v >= 160 and 15 <= s <= 140:
            warm += 1
    return warm / len(pixels)


def measure_map_surface(
    rgb,
    *,
    roi_norms: tuple[float, float, float, float] = DEFAULT_MAP_INTERIOR_NORMS,
) -> MapSurfaceStats:
    """Compute legend + interior discriminators."""
    from PIL import ImageFilter, ImageStat

    w, h = rgb.size
    box = _roi_box(w, h, roi_norms)
    crop = rgb.crop(box)
    gray = crop.convert("L")
    gw, gh = gray.size
    tile = 16
    tile_vars: list[float] = []
    for y0 in range(0, max(1, gh - tile + 1), tile):
        for x0 in range(0, max(1, gw - tile + 1), tile):
            cell = gray.crop((x0, y0, min(gw, x0 + tile), min(gh, y0 + tile)))
            if cell.size[0] < 4 or cell.size[1] < 4:
                continue
            v = float(ImageStat.Stat(cell).var[0]) / (255.0 * 255.0)
            tile_vars.append(v)
    variance = sum(tile_vars) / max(1, len(tile_vars))

    pixels = _hsv_pixels(crop)
    sat_vals = [s for _h, s, _v in pixels]
    hue_hist = [0] * 16
    for h_v, s_v, _v in pixels:
        if s_v >= 40:
            hue_hist[min(15, h_v * 16 // 256)] += 1
    n = max(1, len(sat_vals))
    saturation_mean = (sum(sat_vals) / n) / 255.0
    hue_bins_used = sum(1 for c in hue_hist if c > n * 0.02)

    edges = gray.filter(ImageFilter.FIND_EDGES)
    edge_density = float(ImageStat.Stat(edges).mean[0]) / 255.0
    mean_luma = float(ImageStat.Stat(gray).mean[0]) / 255.0

    return MapSurfaceStats(
        variance=variance,
        saturation_mean=saturation_mean,
        hue_bins_used=hue_bins_used,
        edge_density=edge_density,
        mean_luma=mean_luma,
        legend_warm_left=_legend_warm_fraction(rgb, LEFT_LEGEND_NORMS),
        legend_warm_right=_legend_warm_fraction(rgb, RIGHT_LEGEND_NORMS),
        sample_pixels=n,
        roi_norms=roi_norms,
    )


def check_map_surface(
    rgb,
    *,
    roi_norms: tuple[float, float, float, float] = DEFAULT_MAP_INTERIOR_NORMS,
    legend_warm_min: float = DEFAULT_LEGEND_WARM_MIN,
    variance_max: float = DEFAULT_OVERLAY_VARIANCE_MAX,
    saturation_min: float = DEFAULT_OVERLAY_SATURATION_MIN,
    edge_density_max: float = DEFAULT_OVERLAY_EDGE_DENSITY_MAX,
    min_mean_luma: float = DEFAULT_MIN_MEAN_LUMA,
) -> MapSurfaceCheck:
    """Return whether Map Overlay (political / settlements legends) is open."""
    stats = measure_map_surface(rgb, roi_norms=roi_norms)
    if stats.mean_luma < min_mean_luma and max(stats.legend_warm_left, stats.legend_warm_right) < legend_warm_min:
        result = MapSurfaceCheck(
            is_map_overlay=False,
            stats=stats,
            detail="too_dark_unusable",
        )
        _LOGGER.info("map_surface: %s", result.as_log_dict())
        return result

    # Primary: either legend panel lights up with parchment when overlay is open.
    left_up = stats.legend_warm_left >= legend_warm_min
    right_up = stats.legend_warm_right >= legend_warm_min
    if left_up and right_up:
        detail = "legends_both"
        is_overlay = True
    elif left_up or right_up:
        detail = "legend_left" if left_up else "legend_right"
        is_overlay = True
    else:
        # Secondary: rare opaque fills (keep for non-Remastered / future).
        low_var = stats.variance <= variance_max
        high_sat = stats.saturation_mean >= saturation_min
        few_edges = stats.edge_density <= edge_density_max
        is_overlay = low_var and high_sat and few_edges
        detail = "low_variance_high_sat_low_edges" if is_overlay else "textured_map"

    result = MapSurfaceCheck(is_map_overlay=is_overlay, stats=stats, detail=detail)
    _LOGGER.info("map_surface: %s", result.as_log_dict())
    return result


def estimate_feature_scale_px(
    rgb,
    *,
    roi_norms: tuple[float, float, float, float] = DEFAULT_MAP_INTERIOR_NORMS,
) -> float:
    """Rough on-screen feature scale (px) from edge energy vs blur difference."""
    from PIL import ImageFilter, ImageStat

    w, h = rgb.size
    box = _roi_box(w, h, roi_norms)
    gray = rgb.crop(box).convert("L")
    base = gray.filter(ImageFilter.FIND_EDGES)
    base_e = float(ImageStat.Stat(base).mean[0]) or 1.0
    for radius in range(1, 41):
        blurred = gray.filter(ImageFilter.GaussianBlur(radius=radius))
        edges = blurred.filter(ImageFilter.FIND_EDGES)
        energy = float(ImageStat.Stat(edges).mean[0])
        if energy / base_e <= 0.5:
            return float(radius)
    return 40.0
