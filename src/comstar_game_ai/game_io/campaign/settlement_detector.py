"""
Settlement locator for the Rome Remastered campaign map.

Finds settlement plaque badges in a captured frame and returns pixel positions,
so the actuator has a click point that came from the image rather than from a
model's guess.

Calibrated against one 1280x720 frame at one zoom. Every constant marked CAL
must be re-measured at the canonical pose before this is trusted, and recorded
in docs/design/map-window-projection.md with the window size, per the existing
rule for anchor_scale.
"""

import cv2
import numpy as np

# CAL: OpenCV hue bands, 0-179. One entry per faction colour family.
# RGB swatches: settlements.FACTION_LEGEND_COLOURS / campaign_ui_atlas legend.
# Badge rings = darker rim / lighter core of the same hue family.
#
# Do NOT widen red past ~8: H∈[0,15] floods orange terrain and merges blobs.
# Blue (Scipii) shares hue with seawater — require high saturation (BAND_SAT_MIN).
# Skip low-sat legend fills (Carthage white, Rebels taupe, Greek olive, Seleucid
# mauve, Macedon black) and Egypt yellow until a high-S live sample exists.
#
# Learned 2026-09-14: legend HSV + live rim @ Arretium after capital_zoom (Home).
BANDS = {
    "red": [(0, 8), (168, 179)],  # Julii
    "green": [(38, 80)],          # Brutii / Gaul (live rim ~49)
    "blue": [(100, 115)],         # Scipii (legend H~107)
    "purple": [(128, 148)],       # S.P.Q.R. (legend H~137)
}

# Per-band minimum saturation (OpenCV 0-255). Blue must sit above seawater
# (median sea S is lower; Scipii badge rim median S ~130–150, S90 ~200).
BAND_SAT_MIN = {
    "red": 80,
    "green": 80,
    "blue": 120,
    "purple": 100,
}

BADGE_D_PX = 28      # CAL: badge diameter at canonical zoom, 1280x720
D_TOL      = 0.20    # CAL: accepted diameter spread
HUD_MARGIN = (46, 46, 46, 64)   # CAL: left, top, right, bottom dead zones


def _band_mask(hsv, band):
    h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    s_min = BAND_SAT_MIN.get(band, 80)
    m = np.zeros(h.shape, bool)
    for lo, hi in BANDS[band]:
        m |= (h >= lo) & (h <= hi) & (s >= s_min) & (v >= 90)
    return m


def _is_badge(mask, cx, cy, r):
    """A badge is a coloured ring around a pale emblem field.

    Rim carries the faction colour, the core does not. A terrain patch bounded
    by region border lines is solid through the middle and fails the core test.
    """
    th = np.linspace(0, 2 * np.pi, 64, endpoint=False)
    h, w = mask.shape

    def frac(rr):
        xs = np.clip((cx + rr * np.cos(th)).astype(int), 0, w - 1)
        ys = np.clip((cy + rr * np.sin(th)).astype(int), 0, h - 1)
        return float(mask[ys, xs].mean())

    return frac(r * 0.45) <= 0.55 and frac(r * 0.85) >= 0.35   # CAL


def detect_settlements(img):
    """Return one entry per settlement plaque badge visible in the frame.

    Armies are excluded structurally: an army banner is a tall rectangle beside
    a walking figure and fails the diameter and roundness gates. No prompt
    instruction is involved.
    """
    h, w = img.shape[:2]
    left, top, right, bottom = HUD_MARGIN
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    hits = []

    for band in BANDS:
        m = _band_mask(hsv, band)
        closed = cv2.morphologyEx(
            m.astype(np.uint8) * 255, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8)
        )
        n, _, stats, cent = cv2.connectedComponentsWithStats(closed, 8)
        for i in range(1, n):
            x, y, bw, bh, area = stats[i]
            cx, cy = cent[i]
            if cx < left or cy < top or cx > w - right or cy > h - bottom:
                continue
            if not (BADGE_D_PX * (1 - D_TOL) <= bw <= BADGE_D_PX * (1 + D_TOL)):
                continue
            if not (BADGE_D_PX * (1 - D_TOL) <= bh <= BADGE_D_PX * (1 + D_TOL)):
                continue
            if not (0.8 <= bw / bh <= 1.25):
                continue
            if not _is_badge(m, cx, cy, (bw + bh) / 4.0):
                continue
            hits.append({
                "faction_colour": band,
                "badge_px": (int(round(cx)), int(round(cy))),
                "badge_d": int(round((bw + bh) / 2)),
                "name_crop": _name_crop_box(cx, cy, (bw + bh) / 2.0, w, h),
                "click_px": None,   # filled by click_point(), see below
            })

    return sorted(hits, key=lambda d: d["badge_px"][0])


def _name_crop_box(cx, cy, d, w, h):
    """Box covering the name and region text, which sit immediately right of
    the badge. Feed this crop to OCR, or to the vision agent if OCR struggles
    with the game font. Reading text is what that model is actually good at."""
    x0 = int(cx + d * 0.45)
    x1 = int(min(w - 1, cx + d * 5.0))     # CAL: longest observed plaque
    y0 = int(max(0, cy - d * 0.75))
    y1 = int(min(h - 1, cy + d * 0.75))
    return (x0, y0, x1, y1)


# CAL, and blocking. The badge is at the plaque's left end; the plaque floats
# above the settlement. The clickable thing is the town oval on the ground.
# Measure this offset at the canonical pose by clicking a known settlement and
# bisecting until the move cursor appears. It is zoom dependent, so it belongs
# beside anchor_scale and is void if the pose changes.
CLICK_OFFSET_PX = (None, None)


def click_point(hit):
    dx, dy = CLICK_OFFSET_PX
    if dx is None:
        raise NotImplementedError(
            "CLICK_OFFSET_PX not measured at the canonical pose. "
            "Clicking the badge selects the plaque, not the settlement."
        )
    bx, by = hit["badge_px"]
    return (bx + dx, by + dy)


def rank_targets(hits, army_px, stance_of):
    """Order candidates by attack tier, then by screen distance to the army.

    ``stance_of`` maps a faction colour (or owner key) to an attack tier:
    ``rebel`` | ``enemy`` | ``neutral`` | ``ally``. Exhaust an earlier tier
    before any later one. Colour alone is not enough — source stance from
    diplomacy / belief (rebels via owner id) and pass it in.

    Screen distance is a proxy for march distance and a poor one. The map is
    drawn in perspective, so equal pixel distances are unequal map distances,
    and a settlement across a mountain range or a strait is near on screen and
    far in turns. Use this to order candidates for a first milestone only, and
    replace it with the pathfinder's turns-to-reach before any of it counts as
    target selection.
    """
    rank = {"rebel": 0, "enemy": 1, "neutral": 2, "ally": 3}
    ax, ay = army_px
    scored = []
    for h in hits:
        stance = stance_of.get(h["faction_colour"])
        if stance is None:
            continue                      # unknown colour is not a target
        if stance == "at_war":
            stance = "enemy"
        if stance not in rank:
            continue
        bx, by = h["badge_px"]
        scored.append((rank[stance], (bx - ax) ** 2 + (by - ay) ** 2, h))
    scored.sort(key=lambda t: (t[0], t[1]))
    return [h for _, _, h in scored]


if __name__ == "__main__":
    import sys, json
    img = cv2.imread(sys.argv[1])
    out = detect_settlements(img)
    h, w = img.shape[:2]
    for d in out:
        x, y = d["badge_px"]
        print(json.dumps({**d, "norm": [round(x / w, 4), round(y / h, 4)]}))
