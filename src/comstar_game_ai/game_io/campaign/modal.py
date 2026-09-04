"""Dismiss or handle campaign modals without accepting deals or pausing the game."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from comstar_game_ai.game_io.campaign.ui_mode import (
    CampaignUiMode,
    UiClassification,
    grab_rgb_image,
    grab_and_classify,
)
from comstar_game_ai.game_io.input.send_input import SendInputController
from comstar_game_ai.shared.config import load_config

_LOGGER = logging.getLogger(__name__)

# Decline / close — never the Accept button (typically lower-right of the scroll).
DEFAULT_DECLINE_NORMS: list[tuple[float, float]] = [
    # Diplomacy / negotiation reject button (red X) is usually near center-bottom.
    (0.52, 0.78),
    (0.50, 0.79),
    (0.54, 0.78),
    # Fallbacks for smaller advisor / event popups.
    (0.42, 0.78),
    (0.45, 0.76),
]
DEFAULT_CLOSE_NORMS: list[tuple[float, float]] = [
    (0.66, 0.24),
    (0.70, 0.22),
    (0.68, 0.28),
    (0.61, 0.25),
]
# News / advisor "continue" — center-bottom, not Accept.
DEFAULT_CONTINUE_NORMS: list[tuple[float, float]] = [
    (0.48, 0.78),
    (0.50, 0.78),
    (0.50, 0.82),
]


def _norm_list(raw: object, fallback: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if not isinstance(raw, (list, tuple)):
        return list(fallback)
    out: list[tuple[float, float]] = []
    for item in raw:
        if isinstance(item, (list, tuple)) and len(item) == 2:
            out.append((float(item[0]), float(item[1])))
    return out or list(fallback)


def _to_float(v: object) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if 0.0 <= f <= 1.0:
        return f
    return None


@dataclass(frozen=True)
class ModalActionCandidate:
    action: str
    x_norm: float
    y_norm: float
    confidence: float


@dataclass(frozen=True)
class ModalVisionResult:
    request_id: str
    modal_kind: str
    candidates: tuple[ModalActionCandidate, ...]
    dialog_bounds_norm: tuple[float, float, float, float] | None
    reason: str = ""

    @property
    def best_safe(self) -> ModalActionCandidate | None:
        safe = [c for c in self.candidates if c.action in {"reject", "close", "continue"}]
        return max(safe, key=lambda c: c.confidence) if safe else None

    @property
    def best_unsafe(self) -> ModalActionCandidate | None:
        bad = [c for c in self.candidates if c.action not in {"reject", "close", "continue"}]
        return max(bad, key=lambda c: c.confidence) if bad else None


def _peak_in_mask(
    mask,
    *,
    window: int,
    min_peak: int,
    x0: int,
    y0: int,
    width: int,
    height: int,
) -> ModalActionCandidate | None:
    import numpy as np

    if mask.shape[0] <= window or mask.shape[1] <= window:
        return None
    integral = np.pad(mask.astype(np.int32), ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    scores = (
        integral[window:, window:]
        - integral[:-window, window:]
        - integral[window:, :-window]
        + integral[:-window, :-window]
    )
    flat_index = int(scores.argmax())
    peak = int(scores.flat[flat_index])
    if peak < min_peak:
        return None
    py, px = np.unravel_index(flat_index, scores.shape)
    center_x = x0 + px + window / 2
    center_y = y0 + py + window / 2
    return ModalActionCandidate(
        action="tmp",
        x_norm=float(center_x / width),
        y_norm=float(center_y / height),
        confidence=min(0.95, 0.55 + peak / 200.0),
    )


def _topmost_in_mask(
    mask,
    *,
    window: int,
    min_peak: int,
    x0: int,
    y0: int,
    width: int,
    height: int,
) -> ModalActionCandidate | None:
    """Highest qualifying blob, not the biggest one.

    Used where a larger decoy sits below the target (the alerts trumpet badge is a
    bigger gold blob than the close X directly above it).
    """
    import numpy as np

    if mask.shape[0] <= window or mask.shape[1] <= window:
        return None
    integral = np.pad(mask.astype(np.int32), ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    scores = (
        integral[window:, window:]
        - integral[:-window, window:]
        - integral[window:, :-window]
        + integral[:-window, :-window]
    )
    rows = np.where(scores.max(axis=1) >= min_peak)[0]
    if rows.size == 0:
        return None
    py = int(rows[0])
    px = int(scores[py].argmax())
    peak = int(scores[py, px])
    center_x = x0 + px + window / 2
    center_y = y0 + py + window / 2
    return ModalActionCandidate(
        action="tmp",
        x_norm=float(center_x / width),
        y_norm=float(center_y / height),
        confidence=min(0.95, 0.55 + peak / 200.0),
    )


def left_overlay_parchment_ratio(image) -> float:
    """Fraction of cream UI pixels in the left dock (mission/event panels)."""
    import numpy as np

    rgb = np.asarray(image.convert("RGB"))
    height, width = rgb.shape[:2]
    x1 = max(8, int(width * 0.28))
    y0, y1 = int(height * 0.08), int(height * 0.82)
    roi = rgb[y0:y1, :x1]
    r = roi[:, :, 0].astype(np.int16)
    g = roi[:, :, 1].astype(np.int16)
    b = roi[:, :, 2].astype(np.int16)
    cream = (
        (r >= 165)
        & (g >= 145)
        & (b >= 105)
        & (r <= 245)
        & (g <= 235)
        & (b <= 205)
        & (r >= b + 12)
        & (g >= b + 4)
        & (np.abs(r.astype(np.int16) - g) < 50)
    )
    return float(cream.mean()) if cream.size else 0.0


def _cream_mask(rgb):
    import numpy as np

    r = rgb[:, :, 0].astype(np.int16)
    g = rgb[:, :, 1].astype(np.int16)
    b = rgb[:, :, 2].astype(np.int16)
    return (
        (r >= 165)
        & (g >= 145)
        & (b >= 105)
        & (r <= 245)
        & (g <= 235)
        & (b <= 205)
        & (r >= b + 12)
        & (g >= b + 4)
    )


def panel_bounds(image) -> tuple[int, int, int] | None:
    """(left, right, top) pixels of the largest solid cream panel, or None.

    Covers every panel that owns a close button: the left alerts dock (anchored at
    the window edge) and centred panels such as settlement construction, which
    start around x 0.26 and would be missed by a left-anchored search.
    """
    import numpy as np

    rgb = np.asarray(image.convert("RGB"))
    height, width = rgb.shape[:2]
    cream = _cream_mask(rgb)
    band = cream[int(height * 0.12) : int(height * 0.60), :]
    if band.size == 0:
        return None

    # 0.32, not a majority: senate mission and event cards carry artwork and text
    # blocks that break up the parchment, leaving their columns around 0.37-0.46.
    dense = band.mean(0) > 0.32
    if not dense.any():
        return None
    # Bridge thin gaps (inner borders, tab dividers) before measuring the run.
    gap = max(2, int(width * 0.01))
    filled = dense.copy()
    (idx,) = np.where(dense)
    for start, end in zip(idx[:-1], idx[1:]):
        if end - start <= gap:
            filled[start:end] = True
    edges = np.diff(np.concatenate(([0], filled.view(np.int8), [0])))
    starts = np.where(edges == 1)[0]
    ends = np.where(edges == -1)[0] - 1
    best = int(np.argmax(ends - starts))
    left, right = int(starts[best]), int(ends[best])
    if right - left < width * 0.10:
        return None

    # Measure the top edge on the panel's right portion only: the top-left HUD bar
    # shares columns with a left-docked panel and would mask its real top edge.
    seg_from = max(left, right - max(8, int((right - left) * 0.15)))
    rows = np.where(cream[:, seg_from : right + 1].mean(1) > 0.45)[0]
    if rows.size == 0:
        return None
    top = int(rows.min())
    if top > height * 0.55:
        return None
    return left, right, top


def panel_covers_map_centre(image) -> bool:
    """True when a panel sits over the middle of the screen.

    Settlement and building-browser scrolls straddle the centre and swallow input,
    so they have to be closed even though they ask for no decision. Side cards in
    the left dock leave the centre alone and can simply be left on screen.
    """
    bounds = panel_bounds(image)
    if bounds is None:
        return False
    left, right, _top = bounds
    width = image.size[0]
    return left < width * 0.55 and right > width * 0.45


def blocking_ui_present(image) -> bool:
    """True only for UI that must be cleared before the turn can continue.

    A panel on its own is not blocking. Senate mission and alert cards are notices:
    they carry no accept/reject glyph, the map stays playable behind them, and End
    Turn still works, so treating every panel as a modal just spins on Escape.
    """
    return bool(
        localize_colored_modal_buttons(image)
        or localize_left_panel_decision_buttons(image)
        or panel_covers_map_centre(image)
    )


def localize_panel_close_x(image) -> ModalActionCandidate | None:
    """Find the round gold X that closes a parchment panel.

    Remastered puts it on the panel's top-right corner, centred on the panel edge.
    Clicking it is reliable; Escape leaves some panels (settlement) wide open.
    """
    import numpy as np

    bounds = panel_bounds(image)
    if bounds is None:
        return None
    _left, right_edge, top_edge = bounds

    rgb = np.asarray(image.convert("RGB"))
    height, width = rgb.shape[:2]
    # Hug the corner: the alerts filter funnel and faction crests are gold too, and
    # sit further inside the panel or further out on the map.
    x0 = max(0, right_edge - int(width * 0.012))
    x1 = min(width, right_edge + int(width * 0.012))
    y0 = max(0, top_edge - int(height * 0.018))
    y1 = min(height, top_edge + int(height * 0.05))
    roi = rgb[y0:y1, x0:x1].astype(np.int16)
    if roi.size == 0:
        return None

    r, g, b = roi[:, :, 0], roi[:, :, 1], roi[:, :, 2]
    gold = (
        (r >= 120)
        & (r <= 235)
        & (g >= 70)
        & (g <= 185)
        & (b <= 110)
        & (r >= g + 35)
        & (g >= b + 25)
    )
    peak = _topmost_in_mask(
        gold,
        window=max(10, int(min(width, height) * 0.012)),
        min_peak=18,
        x0=x0,
        y0=y0,
        width=width,
        height=height,
    )
    if peak is None:
        return None

    # The topmost-blob scan anchors on the glyph's upper edge; recentre on the glyph.
    reach = max(8, int(min(width, height) * 0.011))
    px, py = int(peak.x_norm * width), int(peak.y_norm * height)
    bx0, bx1 = max(x0, px - reach), min(x1, px + reach)
    by0, by1 = max(y0, py - reach), min(y1, py + reach)
    local = gold[by0 - y0 : by1 - y0, bx0 - x0 : bx1 - x0]
    if local.any():
        ys, xs = np.where(local)
        px = bx0 + float(xs.mean())
        py = by0 + float(ys.mean())
    return ModalActionCandidate(
        action="close",
        x_norm=float(px / width),
        y_norm=float(py / height),
        confidence=peak.confidence,
    )


def localize_left_panel_decision_buttons(image) -> tuple[ModalActionCandidate, ...]:
    """Find Accept/Reject on left alert/event detail panes (adoption, betrothal, etc.).

    Remastered alert details put circular check/X near the bottom of the expanded
    detail column. Green checks are often olive; require cream UI so map terrain
    does not match.
    """
    import numpy as np

    # These buttons only exist inside a panel docked at the left edge; without one,
    # any green/red pair in this region is terrain, and inside a centred panel it is
    # the building browser's green/red construction lines.
    bounds = panel_bounds(image)
    if bounds is None or bounds[0] > image.size[0] * 0.08:
        return ()

    rgb = np.asarray(image.convert("RGB"))
    height, width = rgb.shape[:2]
    # Cover alerts list + expanded detail (can stretch past mid-left).
    x0, x1 = int(width * 0.10), int(width * 0.55)
    y0, y1 = int(height * 0.48), int(height * 0.90)
    roi = rgb[y0:y1, x0:x1]
    if roi.size == 0:
        return ()

    r = roi[:, :, 0].astype(np.int16)
    g = roi[:, :, 1].astype(np.int16)
    b = roi[:, :, 2].astype(np.int16)
    cream = (
        (r >= 145)
        & (g >= 125)
        & (b >= 85)
        & (r >= b + 8)
        & (g >= b)
        & (np.abs(r - g) < 65)
    )
    if float(cream.mean()) < 0.04:
        return ()

    # Olive/gold-green checks + saturated red Xs on metal discs.
    green = (
        ((g >= 90) & (g >= r + 12) & (g >= b + 12) & (g >= 100))
        | ((g >= 85) & (g >= b + 20) & (r >= 70) & (r <= 160) & (g >= r - 5) & (g >= 95))
    )
    red = (r >= 125) & (r >= g + 28) & (r >= b + 22) & (g <= 135)
    window = max(14, int(min(width, height) * 0.022))

    # Glyph pixels are the check/X themselves, not cream; the cream gate above
    # already establishes that we are looking at a parchment panel.
    accept_peak = _peak_in_mask(
        green, window=window, min_peak=12, x0=x0, y0=y0, width=width, height=height
    )
    reject_peak = _peak_in_mask(
        red, window=window, min_peak=12, x0=x0, y0=y0, width=width, height=height
    )

    out: list[ModalActionCandidate] = []
    accept = (
        ModalActionCandidate("accept", accept_peak.x_norm, accept_peak.y_norm, accept_peak.confidence)
        if accept_peak is not None
        else None
    )
    reject = (
        ModalActionCandidate("reject", reject_peak.x_norm, reject_peak.y_norm, reject_peak.confidence)
        if reject_peak is not None
        else None
    )

    if accept is not None and reject is not None:
        if (
            reject.x_norm > accept.x_norm + 0.005
            and reject.x_norm < accept.x_norm + 0.18
            and abs(reject.y_norm - accept.y_norm) < 0.10
            and reject.y_norm >= 0.55
        ):
            return (accept, reject)
        # Peaks found but not a decision row — fall through to reject-only if plausible.

    if reject is not None and 0.18 <= reject.x_norm <= 0.52 and reject.y_norm >= 0.58:
        # Decision reject without a clean green peak (common on alert cards).
        return (ModalActionCandidate("reject", reject.x_norm, reject.y_norm, reject.confidence),)

    return ()


# Typical Remastered alert-detail reject locations when color localization fails.
LEFT_ALERT_REJECT_FALLBACKS: tuple[tuple[float, float], ...] = (
    (0.40, 0.72),
    (0.38, 0.70),
    (0.42, 0.74),
    (0.36, 0.72),
    (0.44, 0.70),
)


# Measured on a live negotiation (client space): accept 0.453, reject 0.496,
# records 0.540, all at y 0.779. Bands allow for the closing scroll's X at ~0.54.
DIPLOMACY_ACCEPT_X_RANGE = (0.40, 0.52)
DIPLOMACY_REJECT_X_RANGE = (0.44, 0.58)


def centered_scroll_present(image, *, min_cream: float = 0.25, min_delta: float = 0.10) -> bool:
    """True when a big centred parchment scroll fills the screen centre.

    Sunlit terrain trivially satisfies a per-pixel cream test, which is how open
    map frames were being read as negotiation footers. A real scroll instead shows
    a solid cream centre against a dimmed map: measured 0.93 cream and +0.69 luma
    over the edges, versus 0.03 and -0.05 on the campaign map.
    """
    import numpy as np

    rgb = np.asarray(image.convert("RGB")).astype(np.int16)
    height, width = rgb.shape[:2]
    if height < 64 or width < 64:
        return False
    r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
    cream = (
        (r >= 155)
        & (g >= 135)
        & (b >= 95)
        & (r >= b + 12)
        & (g >= b)
        & (np.abs(r - g) < 55)
    )
    luma = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
    box = (
        slice(int(height * 0.20), int(height * 0.80)),
        slice(int(width * 0.30), int(width * 0.70)),
    )
    if float(cream[box].mean()) < min_cream:
        return False
    edges = np.concatenate(
        [
            luma[: int(height * 0.06)].ravel(),
            luma[int(height * 0.94) :].ravel(),
            luma[:, : int(width * 0.06)].ravel(),
            luma[:, int(width * 0.94) :].ravel(),
        ]
    )
    return float(luma[box].mean()) - float(edges.mean()) >= min_delta


def localize_diplomacy_footer_buttons(
    image,
    *,
    require_scroll: bool = True,
) -> tuple[ModalActionCandidate, ...]:
    """Find Accept (green) / Reject (red X) in the centered negotiation scroll footer.

    Remastered diplomacy: reject offer with the red X, then click the adjacent red X
    on the closing scroll to end talks. Map terrain must not match.
    """
    import numpy as np

    if require_scroll and not centered_scroll_present(image):
        return ()

    rgb = np.asarray(image.convert("RGB"))
    height, width = rgb.shape[:2]
    x0, x1 = int(width * 0.36), int(width * 0.68)
    y0, y1 = int(height * 0.68), int(height * 0.88)
    roi = rgb[y0:y1, x0:x1]
    if roi.size == 0:
        return ()

    r = roi[:, :, 0].astype(np.int16)
    g = roi[:, :, 1].astype(np.int16)
    b = roi[:, :, 2].astype(np.int16)

    # Button glyphs are saturated crimson / leaf green. The looser bounds these
    # replace also matched ochre dry earth (170,110,70) and grassland (100,150,70).
    green = (g >= 110) & (r <= 140) & (g >= r + 50) & (g >= b + 40)
    red = (r >= 140) & (g <= 90) & (r >= g + 80) & (r >= b + 60)
    window = max(18, int(min(width, height) * 0.028))
    min_peak = max(16, int(window * window * 0.025))

    accept_peak = _peak_in_mask(
        green, window=window, min_peak=min_peak, x0=x0, y0=y0, width=width, height=height
    )
    reject_peak = _peak_in_mask(
        red, window=window, min_peak=min_peak, x0=x0, y0=y0, width=width, height=height
    )

    def _in(value: float, span: tuple[float, float]) -> bool:
        return span[0] <= value <= span[1]

    accept = (
        ModalActionCandidate("accept", accept_peak.x_norm, accept_peak.y_norm, accept_peak.confidence)
        if accept_peak is not None and _in(accept_peak.x_norm, DIPLOMACY_ACCEPT_X_RANGE)
        else None
    )
    reject = (
        ModalActionCandidate("reject", reject_peak.x_norm, reject_peak.y_norm, reject_peak.confidence)
        if reject_peak is not None and _in(reject_peak.x_norm, DIPLOMACY_REJECT_X_RANGE)
        else None
    )

    if accept is not None and reject is not None:
        # Offer row: reject is immediately right of accept (centered scroll only).
        if (
            reject.x_norm > accept.x_norm + 0.008
            and reject.x_norm < accept.x_norm + 0.14
            and abs(reject.y_norm - accept.y_norm) < 0.06
        ):
            return (accept, reject)
        return ()

    if reject is not None:
        return (reject,)

    if accept is not None:
        return (ModalActionCandidate("continue", accept.x_norm, accept.y_norm, accept.confidence),)

    return ()


def localize_colored_modal_buttons(image) -> tuple[ModalActionCandidate, ...]:
    """Backward-compatible alias: diplomacy footer buttons only."""
    return localize_diplomacy_footer_buttons(image)


def _parse_modal_vision_result(raw: str, request_id: str) -> ModalVisionResult | None:
    text = raw.strip()
    if text.upper().startswith("MODAL_JSON:"):
        text = text.split(":", 1)[1].strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None

    bounds: tuple[float, float, float, float] | None = None
    b = payload.get("dialog_bounds_norm")
    if isinstance(b, (list, tuple)) and len(b) == 4:
        vals = tuple(_to_float(x) for x in b)
        if all(v is not None for v in vals):
            x0, y0, x1, y1 = vals  # type: ignore[misc]
            if x1 > x0 and y1 > y0:
                bounds = (x0, y0, x1, y1)

    out: list[ModalActionCandidate] = []
    for item in payload.get("candidates") or []:
        if not isinstance(item, dict):
            continue
        action = str(item.get("action") or "").strip().lower()
        x = _to_float(item.get("x_norm"))
        y = _to_float(item.get("y_norm"))
        c = _to_float(item.get("confidence"))
        if action and x is not None and y is not None and c is not None:
            out.append(ModalActionCandidate(action=action, x_norm=x, y_norm=y, confidence=c))
    modal_kind = str(payload.get("modal_kind") or "unknown").strip().lower()
    if not out and modal_kind not in {"none", "campaign_map", "main_menu"}:
        return None
    return ModalVisionResult(
        request_id=str(payload.get("request_id") or request_id),
        modal_kind=modal_kind,
        candidates=tuple(out),
        dialog_bounds_norm=bounds,
        reason=str(payload.get("reason") or ""),
    )


def _inside_bounds(x: float, y: float, bounds: tuple[float, float, float, float] | None) -> bool:
    if bounds is None:
        return True
    x0, y0, x1, y1 = bounds
    return x0 <= x <= x1 and y0 <= y <= y1


CENTER_CROP_BOUNDS: tuple[float, float, float, float] = (0.15, 0.08, 0.85, 0.92)
# Alerts / mission docks hug the left edge; the center crop cuts their buttons off.
LEFT_CROP_BOUNDS: tuple[float, float, float, float] = (0.0, 0.04, 0.62, 0.96)


def vision_crop_bounds(image, ui_mode: str = "") -> tuple[float, float, float, float]:
    """Pick the crop sent to Ada: left dock when a left panel is up, else center."""
    if left_overlay_parchment_ratio(image) >= 0.08 or ui_mode == "left_overlay_panel":
        return LEFT_CROP_BOUNDS
    return CENTER_CROP_BOUNDS


def build_modal_vision_prompt(
    *,
    ui_mode: str,
    crop_bounds: tuple[float, float, float, float],
) -> str:
    """Prompt for Ada/LLaVA: name the panel, then locate only glyphs it can see.

    The request id is deliberately absent: with it in the JSON skeleton, llava:7b
    returned the bare id as its whole answer. The caller supplies it instead.
    """
    region = (
        "LEFT side of the game window"
        if tuple(crop_bounds) == LEFT_CROP_BOUNDS
        else "CENTER of the game window"
    )
    return (
        "This is a screenshot crop from Total War: ROME REMASTERED (campaign map).\n"
        f"The crop covers the {region}. Report ONLY what these pixels show.\n"
        "\n"
        "Blocking panels and how they look in this game:\n"
        "1. diplomacy_negotiation - large parchment scroll in the middle. Its footer has a round "
        "GREEN CHECK button (accept the offer) and, just to its right, a round RED X button "
        "(reject the offer / end talks).\n"
        "2. left_alert_panel - cream/parchment column down the left edge with alert cards "
        "(adoption, betrothal, coming of age, senate news). A card that needs a decision shows a "
        "small round OLIVE-GREEN CHECK and a small round RED X side by side near the bottom of the "
        "card text. This panel also has a small round button with a GOLD X on its TOP-RIGHT "
        'corner: report that one as action "close".\n'
        "3. senate_mission - cream scroll on the left offering a mission; it has an accept check "
        "and a red X or a scroll close button.\n"
        "4. advisor_event - small parchment popup with one acknowledge button at bottom center and "
        "no green/red pair.\n"
        "5. pause_menu / pre_battle - dark full-screen menu or battle deployment screen.\n"
        "\n"
        "Rules:\n"
        "- List a button ONLY if you can actually see its glyph (check mark, X, or label). "
        "Never guess a button from the panel shape.\n"
        "- x_norm/y_norm are the button CENTER, normalized to THIS image, 0.0-1.0 "
        "(x_norm=0 is this image's left edge, y_norm=0 its top edge).\n"
        "- Use action \"accept\" for the green check, \"reject\" for the red X, \"close\" for a "
        "close/exit control, \"continue\" for a lone acknowledge button.\n"
        "- confidence is your certainty that the glyph is really there, 0.0-1.0.\n"
        "- If nothing blocks the map (only the map plus the normal bottom HUD bar and minimap), "
        'answer modal_kind "none" with an empty candidate list.\n'
        "\n"
        "- Describe THIS image. Never copy the values or wording out of the examples below.\n"
        "\n"
        "Answer with ONE line, no prose, no code fences, starting with MODAL_JSON: and then one "
        "compact JSON object shaped exactly like this:\n"
        'MODAL_JSON:{"modal_kind":"none|diplomacy_negotiation|'
        'left_alert_panel|senate_mission|advisor_event|pause_menu|pre_battle|other",'
        '"dialog_bounds_norm":[x0,y0,x1,y1],"candidates":[{"action":"accept|reject|close|continue",'
        '"x_norm":0.00,"y_norm":0.00,"confidence":0.00}],"reason":"few words"}\n'
        "\n"
        "Example for a clear campaign map:\n"
        'MODAL_JSON:{"modal_kind":"none","dialog_bounds_norm":[0,0,0,0],"candidates":[],'
        '"reason":"nothing over the map"}\n'
        "\n"
        "Example for a negotiation scroll whose check is left of its X:\n"
        'MODAL_JSON:{"modal_kind":"diplomacy_negotiation",'
        '"dialog_bounds_norm":[0.28,0.20,0.74,0.84],"candidates":['
        '{"action":"accept","x_norm":0.47,"y_norm":0.77,"confidence":0.80},'
        '{"action":"reject","x_norm":0.53,"y_norm":0.77,"confidence":0.85}],'
        '"reason":"green check and red X in scroll footer"}\n'
        "\n"
        "Example for a parchment panel whose only control is the round gold X on its "
        "top-right corner:\n"
        'MODAL_JSON:{"modal_kind":"left_alert_panel",'
        '"dialog_bounds_norm":[0.26,0.21,0.74,1.00],"candidates":['
        '{"action":"close","x_norm":0.74,"y_norm":0.22,"confidence":0.75}],'
        '"reason":"gold X on panel corner"}'
    )


async def _query_modal_vision_async(
    image,
    *,
    request_id: str,
    turn: int | None,
    ui_mode: str,
    timeout_s: float,
) -> ModalVisionResult | None:
    from comstar_game_ai.agent.compositor.views import ViewBudget, compose_reach_images
    from comstar_game_ai.agent.reach.director import call_modal_vision
    from comstar_game_ai.agent.reach.session import ReachSession

    # LLaVA 7B downsamples full-HD frames enough to miss small dialog text/buttons.
    # Analyze the crop that actually contains the panel and translate the returned
    # crop-relative coordinates back to the full game window.
    crop_bounds = vision_crop_bounds(image, ui_mode)
    width, height = image.size
    crop = image.crop(
        (
            int(width * crop_bounds[0]),
            int(height * crop_bounds[1]),
            int(width * crop_bounds[2]),
            int(height * crop_bounds[3]),
        )
    )
    images, _ = compose_reach_images(
        [crop],
        budget=ViewBudget(max_images=1, width=1280, height=720, jpeg_quality=85),
    )
    if not images:
        return None
    prompt = build_modal_vision_prompt(ui_mode=ui_mode, crop_bounds=crop_bounds)
    context = (
        f"turn={turn}. Independently inspect the pixels. "
        "Do not infer screen state from prior context or local classifiers."
    )
    session = ReachSession(enable_game_query=False)
    try:
        await session.start()
        text = await call_modal_vision(
            session,
            text=prompt,
            context=context,
            question_id=request_id,
            images=images,
            timeout=timeout_s,
        )
    finally:
        await session.stop(clear_remote=False)
    if not text:
        print(f"MODAL Ada vision: empty response request_id={request_id}", flush=True)
        return None
    parsed = _parse_modal_vision_result(text, request_id=request_id)
    if parsed is None:
        print(
            f"MODAL Ada vision: unparseable response request_id={request_id} raw={text[:500]!r}",
            flush=True,
        )
        return None
    x0, y0, x1, y1 = crop_bounds
    sx, sy = x1 - x0, y1 - y0
    candidates = tuple(
        ModalActionCandidate(
            action=c.action,
            x_norm=x0 + c.x_norm * sx,
            y_norm=y0 + c.y_norm * sy,
            confidence=c.confidence,
        )
        for c in parsed.candidates
    )
    bounds = None
    if parsed.dialog_bounds_norm is not None:
        bx0, by0, bx1, by1 = parsed.dialog_bounds_norm
        bounds = (x0 + bx0 * sx, y0 + by0 * sy, x0 + bx1 * sx, y0 + by1 * sy)
    return ModalVisionResult(
        request_id=parsed.request_id,
        modal_kind=parsed.modal_kind,
        candidates=candidates,
        dialog_bounds_norm=bounds,
        reason=parsed.reason,
    )


@dataclass
class ModalHandler:
    """Click Decline/Close on scrolls. Never Shift+Enter. Never Escape on a clear map."""

    input_controller: SendInputController = field(default_factory=SendInputController)
    max_attempts: int = 4
    settle_s: float = 0.6
    min_confidence: float = 0.72
    min_margin: float = 0.10
    model_timeout_s: float = 30.0
    save_unresolved_frames: bool = True
    diplomacy_action: str = "reject"
    allow_coordinate_fallback: bool = False
    allow_visual_button_fallback: bool = True
    use_ada_vision: bool = True

    def handle(
        self,
        hwnd: int,
        classification: UiClassification | None = None,
        *,
        turn: int | None = None,
    ) -> UiClassification:
        current = classification or grab_and_classify(hwnd)
        if current.mode == CampaignUiMode.UNKNOWN and current.detail in {"black_capture", "no_frame"}:
            return current

        print(
            f"VISION inspect: local_mode={current.mode.value} conf={current.confidence:.2f} detail={current.detail} "
            f"turn={turn if turn is not None else 'unknown'}",
            flush=True,
        )

        cfg = (load_config().get("campaign") or {}).get("modal") or {}
        self.min_confidence = float(cfg.get("min_confidence", self.min_confidence))
        self.min_margin = float(cfg.get("min_margin", self.min_margin))
        self.model_timeout_s = float(cfg.get("model_timeout_s", self.model_timeout_s))
        self.save_unresolved_frames = bool(cfg.get("save_unresolved_frames", self.save_unresolved_frames))
        self.diplomacy_action = str(cfg.get("diplomacy_action", self.diplomacy_action)).strip().lower()
        self.allow_coordinate_fallback = bool(
            cfg.get("allow_coordinate_fallback", self.allow_coordinate_fallback)
        )
        self.allow_visual_button_fallback = bool(
            cfg.get("allow_visual_button_fallback", self.allow_visual_button_fallback)
        )
        self.use_ada_vision = bool(cfg.get("use_ada_vision", self.use_ada_vision))

        request_id = f"modal-{uuid4().hex[:10]}"
        image = grab_rgb_image(hwnd)
        if image is None:
            print(
                f"MODAL handler: capture FAILED (grab_rgb_image returned None) hwnd={hwnd}",
                flush=True,
            )
            return current

        # Clear campaign map: do not Escape/spam when nothing dismissible is present.
        if current.mode == CampaignUiMode.CAMPAIGN_MAP:
            if (
                not localize_diplomacy_footer_buttons(image)
                and not localize_left_panel_decision_buttons(image)
                and left_overlay_parchment_ratio(image) < 0.10
            ):
                return current

        # Ada vision decides what the panel is and where its buttons are.
        if self.use_ada_vision:
            self._save_unresolved_frame(image, f"{request_id}-raw")
            print(
                f"MODAL Ada vision: calling Reach/Ollama request_id={request_id} "
                f"timeout_s={self.model_timeout_s}",
                flush=True,
            )
            result = self._query_modal_vision_sync(
                image,
                request_id=request_id,
                turn=turn,
                ui_mode=current.mode.value,
            )
            if result is not None:
                acted = self._act_on_vision_result(hwnd, result)
                if acted is not None:
                    return acted

        # Pixel localization backs Ada up when the model sees nothing usable.
        if self.allow_visual_button_fallback:
            clicked = self._click_visual_dismiss(hwnd, image)
            if clicked is not None:
                return clicked

        if self.allow_coordinate_fallback:
            decline = _norm_list(cfg.get("decline_click_norms"), DEFAULT_DECLINE_NORMS)
            close = _norm_list(cfg.get("close_click_norms"), DEFAULT_CLOSE_NORMS)
            cont = _norm_list(cfg.get("continue_click_norms"), DEFAULT_CONTINUE_NORMS)
            for xn, yn in (decline + close + cont)[: self.max_attempts]:
                self._click_norm(hwnd, xn, yn)
                time.sleep(self.settle_s)
                current = grab_and_classify(hwnd)
                if current.mode == CampaignUiMode.CAMPAIGN_MAP:
                    return current
            return current

        if current.mode in {CampaignUiMode.MODAL, CampaignUiMode.PAUSE, CampaignUiMode.PRE_BATTLE}:
            self._save_unresolved_frame(image, f"{request_id}-unresolved")
        print("MODAL handler: no dismissible controls found", flush=True)
        if current.mode == CampaignUiMode.PAUSE:
            self.input_controller.tap_key("escape", dwell_ms=40, hwnd=hwnd)
            time.sleep(self.settle_s)
            return grab_and_classify(hwnd)
        return current

    def _act_on_vision_result(
        self,
        hwnd: int,
        result: ModalVisionResult,
    ) -> UiClassification | None:
        """Click what Ada reported. None means Ada gave nothing safe to act on."""
        coords = ", ".join(
            f"{c.action}=({c.x_norm:.3f},{c.y_norm:.3f})/{c.confidence:.2f}"
            for c in result.candidates
        )
        print(
            f"VISION recognized: modal={result.modal_kind} buttons=[{coords}] "
            f"reason={result.reason!r}",
            flush=True,
        )
        is_diplomacy = "diplomacy" in result.modal_kind or result.modal_kind == "trade"
        preferred = self.diplomacy_action if is_diplomacy else None
        candidate = self._choose_safe_candidate(result, preferred_action=preferred)
        if candidate is None:
            print(f"MODAL Ada vision: no safe candidate (reason={result.reason})", flush=True)
            return None

        print(
            f"MODAL Ada vision: chosen action={candidate.action} conf={candidate.confidence:.2f} "
            f"click_norm=({candidate.x_norm:.3f},{candidate.y_norm:.3f})",
            flush=True,
        )
        self._click_norm(hwnd, candidate.x_norm, candidate.y_norm)

        # Declining an offer opens a closing scroll that needs its own X.
        if is_diplomacy and candidate.action == "reject":
            time.sleep(max(self.settle_s, 0.8))
            return self._click_diplomacy_end_talks(hwnd)

        time.sleep(self.settle_s)
        # An alert card decision can leave the alerts column open.
        after = grab_rgb_image(hwnd)
        if after is not None and panel_bounds(after) is not None:
            print("MODAL Ada vision: dismissing remaining panel", flush=True)
            closed = self._close_panel(hwnd, after, left_overlay_parchment_ratio(after))
            if closed is not None:
                return closed
        return grab_and_classify(hwnd)

    def _click_visual_dismiss(self, hwnd: int, image) -> UiClassification | None:
        """Dismiss blocking UI: diplomacy, left-alert decisions, then left-dock Escape."""
        # 1) Centered diplomacy / scroll footer — never Escape through this.
        visual_candidates = localize_diplomacy_footer_buttons(image)
        reject = next((c for c in visual_candidates if c.action == "reject"), None)
        accept = next((c for c in visual_candidates if c.action == "accept"), None)
        cont = next((c for c in visual_candidates if c.action == "continue"), None)

        if accept is not None and reject is not None:
            print(
                "VISION diplomacy: offer buttons "
                f"accept=({accept.x_norm:.3f},{accept.y_norm:.3f}) "
                f"reject=({reject.x_norm:.3f},{reject.y_norm:.3f}); "
                "clicking reject, then end-talks X",
                flush=True,
            )
            self._click_norm(hwnd, reject.x_norm, reject.y_norm)
            time.sleep(max(self.settle_s, 0.8))
            return self._click_diplomacy_end_talks(hwnd)

        if reject is not None:
            print(
                "VISION diplomacy: end-talks / lone reject "
                f"reject=({reject.x_norm:.3f},{reject.y_norm:.3f}); clicking",
                flush=True,
            )
            self._click_norm(hwnd, reject.x_norm, reject.y_norm)
            time.sleep(self.settle_s)
            return grab_and_classify(hwnd)

        if cont is not None:
            print(
                "VISION modal: acknowledge/continue "
                f"continue=({cont.x_norm:.3f},{cont.y_norm:.3f}); clicking",
                flush=True,
            )
            self._click_norm(hwnd, cont.x_norm, cont.y_norm)
            time.sleep(self.settle_s)
            return grab_and_classify(hwnd)

        # 2) Left alert/event detail decisions (betrothal, etc.) — reject before Escape.
        left_decision = localize_left_panel_decision_buttons(image)
        left_reject = next((c for c in left_decision if c.action == "reject"), None)
        left_accept = next((c for c in left_decision if c.action == "accept"), None)
        if left_accept is not None and left_reject is not None:
            print(
                "VISION alert panel: decision buttons "
                f"accept=({left_accept.x_norm:.3f},{left_accept.y_norm:.3f}) "
                f"reject=({left_reject.x_norm:.3f},{left_reject.y_norm:.3f}); clicking reject",
                flush=True,
            )
            self._click_norm(hwnd, left_reject.x_norm, left_reject.y_norm)
            time.sleep(max(self.settle_s, 0.7))
            # Decision may leave the alerts list open — close it via its own X.
            after = grab_rgb_image(hwnd)
            if after is not None and panel_bounds(after) is not None:
                print("VISION alert panel: dismissing remaining panel", flush=True)
                closed = self._close_panel(hwnd, after, left_overlay_parchment_ratio(after))
                if closed is not None:
                    return closed
            return grab_and_classify(hwnd)

        # 3) Any parchment panel with a close X: alerts dock, settlement, mission.
        before_left = left_overlay_parchment_ratio(image)
        if panel_bounds(image) is not None or before_left >= 0.10:
            closed = self._close_panel(hwnd, image, before_left)
            if closed is not None:
                return closed
            return grab_and_classify(hwnd)

        return None

    def _close_panel(self, hwnd: int, image, before_left: float) -> UiClassification | None:
        """Click the panel's close X, falling back to Escape if it cannot be found."""
        close = localize_panel_close_x(image)
        if close is not None:
            bounds = panel_bounds(image)
            print(
                f"VISION panel: bounds={bounds} parchment_ratio={before_left:.3f}; clicking close X "
                f"close=({close.x_norm:.3f},{close.y_norm:.3f}) conf={close.confidence:.2f}",
                flush=True,
            )
            self._click_norm(hwnd, close.x_norm, close.y_norm)
            time.sleep(self.settle_s)
            after_image = grab_rgb_image(hwnd)
            if after_image is None or panel_bounds(after_image) is None:
                print("VISION panel: close X cleared the panel", flush=True)
                return grab_and_classify(hwnd)
            # A stacked panel can reveal another one behind it; report and let the
            # next round handle it rather than falling through to Escape spam.
            print(
                f"VISION panel: still present after close X (bounds={panel_bounds(after_image)})",
                flush=True,
            )
            return grab_and_classify(hwnd)

        if not blocking_ui_present(image):
            print(
                f"VISION panel: notice only (parchment_ratio={before_left:.3f}, no decision, "
                "no close X); leaving it and continuing",
                flush=True,
            )
            return grab_and_classify(hwnd)

        print(
            f"VISION panel: parchment_ratio={before_left:.3f}; no close X found, pressing Escape",
            flush=True,
        )
        self.input_controller.tap_key("escape", dwell_ms=40, hwnd=hwnd)
        time.sleep(self.settle_s)
        return grab_and_classify(hwnd)

    def _click_diplomacy_end_talks(self, hwnd: int) -> UiClassification:
        """After declining an offer, click the adjacent red X that ends negotiations."""
        image = grab_rgb_image(hwnd)
        if image is None:
            return grab_and_classify(hwnd)
        # Prefer a fresh lone reject; if the offer pair is still visible, click reject again.
        candidates = localize_diplomacy_footer_buttons(image)
        reject = next((c for c in candidates if c.action == "reject"), None)
        accept = next((c for c in candidates if c.action == "accept"), None)
        if reject is not None:
            label = "end-talks X" if accept is None else "reject again"
            print(
                f"VISION diplomacy: {label} "
                f"reject=({reject.x_norm:.3f},{reject.y_norm:.3f}); clicking",
                flush=True,
            )
            self._click_norm(hwnd, reject.x_norm, reject.y_norm)
            time.sleep(self.settle_s)
            # One more pass if a closing X remains.
            image2 = grab_rgb_image(hwnd)
            if image2 is not None:
                candidates2 = localize_diplomacy_footer_buttons(image2)
                reject2 = next((c for c in candidates2 if c.action == "reject"), None)
                accept2 = next((c for c in candidates2 if c.action == "accept"), None)
                if reject2 is not None and accept2 is None:
                    print(
                        "VISION diplomacy: final end-talks X "
                        f"reject=({reject2.x_norm:.3f},{reject2.y_norm:.3f}); clicking",
                        flush=True,
                    )
                    self._click_norm(hwnd, reject2.x_norm, reject2.y_norm)
                    time.sleep(self.settle_s)
        else:
            print("VISION diplomacy: no end-talks X after reject", flush=True)
        return grab_and_classify(hwnd)

    def _save_unresolved_frame(self, image, request_id: str) -> None:
        if not self.save_unresolved_frames:
            return
        try:
            out = Path("data/runtime") / f"modal-unresolved-{request_id}.png"
            out.parent.mkdir(parents=True, exist_ok=True)
            image.save(out)
            _LOGGER.info("modal_vision unresolved frame saved: %s", out.as_posix())
        except Exception:
            _LOGGER.debug("failed to save unresolved modal frame", exc_info=True)

    def _query_modal_vision_sync(
        self,
        image,
        *,
        request_id: str,
        turn: int | None,
        ui_mode: str,
    ) -> ModalVisionResult | None:
        try:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop is not None and loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                    future = ex.submit(
                        asyncio.run,
                        _query_modal_vision_async(
                            image,
                            request_id=request_id,
                            turn=turn,
                            ui_mode=ui_mode,
                            timeout_s=self.model_timeout_s,
                        ),
                    )
                    return future.result(timeout=self.model_timeout_s + 5.0)
            else:
                return asyncio.run(
                    _query_modal_vision_async(
                        image,
                        request_id=request_id,
                        turn=turn,
                        ui_mode=ui_mode,
                        timeout_s=self.model_timeout_s,
                    )
                )
        except Exception as exc:
            print(
                f"MODAL Ada vision: FAILED request_id={request_id} error={type(exc).__name__}: {exc}",
                flush=True,
            )
            _LOGGER.warning("modal_vision query failed: %s", exc, exc_info=True)
            return None

    def _choose_safe_candidate(
        self,
        result: ModalVisionResult,
        *,
        preferred_action: str | None = None,
    ) -> ModalActionCandidate | None:
        candidates = [
            c
            for c in result.candidates
            if c.action in {"reject", "close", "continue"}
            and (preferred_action is None or c.action == preferred_action)
        ]
        best_safe = max(candidates, key=lambda c: c.confidence) if candidates else None
        if best_safe is None:
            return None
        if best_safe.confidence < self.min_confidence:
            return None
        if not _inside_bounds(best_safe.x_norm, best_safe.y_norm, result.dialog_bounds_norm):
            return None
        best_unsafe = result.best_unsafe
        if best_unsafe is not None and (best_safe.confidence - best_unsafe.confidence) < self.min_margin:
            return None
        return best_safe

    def _click_norm(self, hwnd: int, x_norm: float, y_norm: float) -> bool:
        return self.input_controller.click_client_norm(hwnd, x_norm, y_norm, dwell_ms=40)


def ensure_campaign_map(
    hwnd: int | None,
    *,
    input_controller: SendInputController | None = None,
    max_rounds: int = 4,
    turn: int | None = None,
) -> UiClassification:
    """Classify and dismiss until map or give up. No hwnd → UNKNOWN (no clicks).

    Multiple rounds cover offer → closing scroll → map (each needs its own reject click).
    """
    if hwnd is None:
        return grab_and_classify(None)
    handler = ModalHandler(input_controller=input_controller or SendInputController())
    last = grab_and_classify(hwnd)
    for _ in range(max_rounds):
        if last.mode == CampaignUiMode.UNKNOWN and last.detail in {"black_capture", "no_frame"}:
            return last
        last = handler.handle(hwnd, last, turn=turn)
        image = grab_rgb_image(hwnd)
        if image is None:
            return last
        overlay = left_overlay_parchment_ratio(image)
        buttons = localize_colored_modal_buttons(image) or localize_left_panel_decision_buttons(image)
        clear = (
            last.mode == CampaignUiMode.CAMPAIGN_MAP
            and overlay < 0.08
            and not buttons
        )
        if clear:
            return last
    return last
