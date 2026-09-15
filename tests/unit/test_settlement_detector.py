"""CV badge detector — locate plaques without model coordinates."""

from __future__ import annotations

from pathlib import Path

import cv2
import pytest

from comstar_game_ai.game_io.campaign.settlement_detector import (
    CLICK_OFFSET_PX,
    click_point,
    detect_settlements,
)

REF = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "runtime"
    / "view_besiege"
    / "20260911-220517_qwen3vl_frame.jpg"
)

# Hand-measured badge centres on the reference frame (handoff §1.1).
# Segesta is occluded by a debug reticle in that capture and is expected miss.
EXPECTED = {
    "arretium": (0.466, 0.628),
    "patavium": (0.570, 0.285),
    "ariminum": (0.699, 0.528),
}


@pytest.mark.skipif(not REF.is_file(), reason="reference frame not on disk")
def test_detect_settlements_on_reference_frame():
    img = cv2.imread(str(REF))
    assert img is not None
    h, w = img.shape[:2]
    hits = detect_settlements(img)
    assert len(hits) >= 3
    assert all(h["click_px"] is None for h in hits)
    norms = [(hx["badge_px"][0] / w, hx["badge_px"][1] / h) for hx in hits]
    colours = {hx["faction_colour"] for hx in hits}
    assert "red" in colours and "green" in colours

    for name, (ex, ey) in EXPECTED.items():
        nearest = min(norms, key=lambda p: (p[0] - ex) ** 2 + (p[1] - ey) ** 2)
        err = ((nearest[0] - ex) ** 2 + (nearest[1] - ey) ** 2) ** 0.5
        assert err < 0.03, f"{name}: nearest={nearest} expected=({ex},{ey}) err={err}"


def test_click_point_raises_until_offset_measured():
    assert CLICK_OFFSET_PX == (None, None)
    with pytest.raises(NotImplementedError, match="CLICK_OFFSET_PX"):
        click_point({"badge_px": (100, 200)})
