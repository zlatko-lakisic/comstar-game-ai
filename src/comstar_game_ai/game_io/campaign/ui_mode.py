"""Classify campaign UI from a window capture (map vs modal vs pause)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from comstar_game_ai.game_io.state_machine import GameState

if TYPE_CHECKING:
    from comstar_game_ai.game_io.capture.window_capture import CaptureFrame

_LOGGER = logging.getLogger(__name__)


class CampaignUiMode(str, Enum):
    CAMPAIGN_MAP = "campaign_map"
    MODAL = "modal"
    PRE_BATTLE = "pre_battle"
    PAUSE = "pause"
    UNKNOWN = "unknown"


MODAL_MODES = frozenset(
    {
        CampaignUiMode.MODAL,
        CampaignUiMode.PRE_BATTLE,
        CampaignUiMode.PAUSE,
    }
)


@dataclass(frozen=True)
class UiClassification:
    mode: CampaignUiMode
    confidence: float
    parchment_ratio: float = 0.0
    center_variance: float = 0.0
    edge_luminance: float = 0.0
    center_luminance: float = 0.0
    detail: str = ""

    def blocks_campaign_orders(self) -> bool:
        return self.mode in MODAL_MODES

    def to_game_state(self) -> GameState | None:
        if self.mode == CampaignUiMode.CAMPAIGN_MAP:
            return GameState.CAMPAIGN_MAP
        if self.mode == CampaignUiMode.MODAL:
            return GameState.CAMPAIGN_MODAL
        if self.mode == CampaignUiMode.PRE_BATTLE:
            return GameState.PRE_BATTLE_SCROLL
        if self.mode == CampaignUiMode.PAUSE:
            return GameState.CAMPAIGN_MODAL
        return None


def _bgra_to_rgb_image(frame: CaptureFrame):
    from PIL import Image

    # MSS returns BGRA (4 bytes per pixel); PrintWindow returns BGRX (also 4 bytes).
    # PIL "BGRX" decoder handles both since it ignores the 4th channel.
    raw_mode = "BGRX" if frame.backend != "mss" else "BGRA"
    try:
        return Image.frombytes("RGB", (frame.width, frame.height), frame.data, "raw", raw_mode)
    except Exception:
        # If size mismatch, try the other mode
        alt = "BGRA" if raw_mode == "BGRX" else "BGRX"
        return Image.frombytes("RGB", (frame.width, frame.height), frame.data, "raw", alt)


def _clamp_box(w: int, h: int, box: tuple[int, int, int, int]) -> tuple[int, int, int, int] | None:
    x0, y0, x1, y1 = box
    x0 = max(0, min(w, x0))
    x1 = max(0, min(w, x1))
    y0 = max(0, min(h, y0))
    y1 = max(0, min(h, y1))
    if x1 - x0 < 2 or y1 - y0 < 2:
        return None
    return (x0, y0, x1, y1)


def _region_stats(rgb, box: tuple[int, int, int, int], *, step: int = 8) -> tuple[float, float, float]:
    """Return (parchment_ratio, luminance, variance) for a crop."""
    clamped = _clamp_box(rgb.size[0], rgb.size[1], box)
    if clamped is None:
        return 0.0, 0.0, 0.0
    crop = rgb.crop(clamped)
    w, h = crop.size
    if w < 2 or h < 2:
        return 0.0, 0.0, 0.0
    parchment = 0
    n = 0
    lumas: list[float] = []
    px = crop.load()
    for y in range(0, h, step):
        for x in range(0, w, step):
            r, g, b = px[x, y][:3]
            luma = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
            lumas.append(luma)
            # Parchment / cream UI: warm, mid-bright, low saturation-to-blue.
            warm = r >= 150 and g >= 110 and b <= 170 and r >= b + 15 and g >= b
            if warm:
                parchment += 1
            n += 1
    if not n:
        return 0.0, 0.0, 0.0
    mean = sum(lumas) / n
    var = sum((v - mean) ** 2 for v in lumas) / n
    return parchment / n, mean, var


def classify_campaign_image(rgb) -> UiClassification:
    """
    Cheap layout heuristic — not OCR.

    Open stratmap: high color variance in the center, mixed terrain.
    Modal / trade / advisor scroll: warm parchment rectangle, darkened edges.
    Pause: overall dark, low parchment, low variance.
    """
    w, h = rgb.size
    if w < 64 or h < 64:
        return UiClassification(mode=CampaignUiMode.UNKNOWN, confidence=0.0, detail="frame_too_small")

    cx0, cy0 = int(w * 0.28), int(h * 0.20)
    cx1, cy1 = int(w * 0.72), int(h * 0.80)
    parchment, center_luma, center_var = _region_stats(rgb, (cx0, cy0, cx1, cy1))

    # Thin edge strips (HUD / darkened overlay)
    edge_boxes = (
        (0, 0, w, max(8, int(h * 0.10))),
        (0, int(h * 0.90), w, h),
        (0, 0, max(8, int(w * 0.08)), h),
        (int(w * 0.92), 0, w, h),
    )
    edge_lumas = [_region_stats(rgb, box)[1] for box in edge_boxes]
    edge_luma = sum(edge_lumas) / max(len(edge_lumas), 1)

    # PrintWindow often returns a black frame on DX games — that is not the pause menu.
    if center_luma < 0.06 and edge_luma < 0.06 and parchment < 0.02:
        return UiClassification(
            mode=CampaignUiMode.UNKNOWN,
            confidence=0.0,
            parchment_ratio=parchment,
            center_variance=center_var,
            edge_luminance=edge_luma,
            center_luminance=center_luma,
            detail="black_capture",
        )

    # Pause: dim everywhere, little parchment, but not a dead capture.
    if center_luma < 0.22 and edge_luma < 0.20 and parchment < 0.08:
        return UiClassification(
            mode=CampaignUiMode.PAUSE,
            confidence=0.75,
            parchment_ratio=parchment,
            center_variance=center_var,
            edge_luminance=edge_luma,
            center_luminance=center_luma,
            detail="dark_low_variance",
        )

    # Modal: parchment-heavy center, edges darker than center.
    if parchment >= 0.18 and center_luma > edge_luma + 0.08:
        return UiClassification(
            mode=CampaignUiMode.MODAL,
            confidence=min(0.95, 0.55 + parchment),
            parchment_ratio=parchment,
            center_variance=center_var,
            edge_luminance=edge_luma,
            center_luminance=center_luma,
            detail="parchment_center",
        )

    # Left mission/event dock: cream panel on the left while map remains visible.
    # Only a decision to make (or a panel over the centre) counts as a modal — a
    # senate mission or alert notice leaves the map playable, and calling it a modal
    # strands the turn on a panel that has nothing to dismiss.
    from comstar_game_ai.game_io.campaign.modal import (
        blocking_ui_present,
        left_overlay_parchment_ratio,
    )

    left_ratio = left_overlay_parchment_ratio(rgb)
    blocking = blocking_ui_present(rgb)
    if blocking:
        return UiClassification(
            mode=CampaignUiMode.MODAL,
            confidence=min(0.92, 0.55 + max(left_ratio, parchment)),
            parchment_ratio=max(parchment, left_ratio),
            center_variance=center_var,
            edge_luminance=edge_luma,
            center_luminance=center_luma,
            detail="left_overlay_panel" if left_ratio >= 0.10 else "panel_over_centre",
        )

    # Map: varied terrain in the center (PrintWindow frames are often mildly noisy).
    # Nothing is asking for a decision and nothing covers the centre at this point, so
    # a notice card or HUD chrome lifting the parchment ratio does not make this a
    # modal — reporting "unknown" here only stranded the turn on a playable map.
    if center_var >= 0.005 and center_luma > 0.18:
        return UiClassification(
            mode=CampaignUiMode.CAMPAIGN_MAP,
            confidence=0.7 if parchment < 0.16 else 0.6,
            parchment_ratio=parchment,
            center_variance=center_var,
            edge_luminance=edge_luma,
            center_luminance=center_luma,
            detail="high_center_variance" if parchment < 0.16 else "map_with_overlay",
        )

    # Winter and night cameras are dim and nearly flat, so the bright-map test above
    # misses them. A lit HUD frame around a dimmer centre still means the stratmap:
    # the pause menu and a dead capture both darken the edges too, and are already
    # handled above.
    if center_luma > 0.06 and center_var >= 0.0015 and edge_luma >= 0.20:
        return UiClassification(
            mode=CampaignUiMode.CAMPAIGN_MAP,
            confidence=0.6,
            parchment_ratio=parchment,
            center_variance=center_var,
            edge_luminance=edge_luma,
            center_luminance=center_luma,
            detail="dim_map_with_lit_hud",
        )

    return UiClassification(
        mode=CampaignUiMode.UNKNOWN,
        confidence=0.3,
        parchment_ratio=parchment,
        center_variance=center_var,
        edge_luminance=edge_luma,
        center_luminance=center_luma,
        detail="no_strong_signal",
    )


def classify_frame(frame: CaptureFrame | None) -> UiClassification:
    if frame is None or not frame.data or frame.width < 64 or frame.height < 64:
        return UiClassification(mode=CampaignUiMode.UNKNOWN, confidence=0.0, detail="no_frame")
    try:
        rgb = _bgra_to_rgb_image(frame)
        return classify_campaign_image(rgb)
    except Exception as exc:
        _LOGGER.warning("classify_frame failed: %s", exc)
        return UiClassification(mode=CampaignUiMode.UNKNOWN, confidence=0.0, detail=str(exc))


def grab_and_classify(hwnd: int | None) -> UiClassification:
    """Capture the game client and classify. No hwnd → UNKNOWN (safe for dry tests)."""
    if not hwnd:
        return UiClassification(mode=CampaignUiMode.UNKNOWN, confidence=0.0, detail="no_hwnd")
    try:
        from comstar_game_ai.game_io.capture.window_capture import WindowCapture

        return classify_frame(WindowCapture(hwnd).grab())
    except Exception as exc:
        _LOGGER.debug("grab_and_classify failed: %s", exc)
        return UiClassification(mode=CampaignUiMode.UNKNOWN, confidence=0.0, detail=str(exc))


def grab_rgb_image(hwnd: int | None):
    """Capture game client frame as an RGB PIL image."""
    if not hwnd:
        return None
    try:
        from comstar_game_ai.game_io.capture.window_capture import WindowCapture

        frame = WindowCapture(hwnd).grab()
        if frame is None or not frame.data or frame.width < 2 or frame.height < 2:
            return None
        return _bgra_to_rgb_image(frame)
    except Exception as exc:
        _LOGGER.debug("grab_rgb_image failed: %s", exc)
        return None


def save_debug_capture(hwnd: int | None, out_path: str) -> bool:
    """Persist one raw RGB frame for debugging stuck dialogs."""
    try:
        from pathlib import Path

        img = grab_rgb_image(hwnd)
        if img is None:
            return False
        target = Path(out_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        img.save(target)
        return True
    except Exception as exc:
        _LOGGER.debug("save_debug_capture failed: %s", exc)
        return False
