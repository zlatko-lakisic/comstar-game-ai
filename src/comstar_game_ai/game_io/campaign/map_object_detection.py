"""AO object-detection client for campaign map frames.

Calls ``type: object_detection`` agents via Reach ``direct_agent`` and parses
typed ``detections[]`` JSON. Do **not** run prose sanitizers on the answer —
AO already returns structured JSON (see AO object_detection_runtime).
"""

from __future__ import annotations

import json
import logging
import math
import re
from dataclasses import dataclass
from typing import Any, Sequence

_LOGGER = logging.getLogger(__name__)

#: Fixed v1 class names for custom RTW YOLOX (order = class id).
RTW_CLASS_NAMES: tuple[str, ...] = (
    "settlement_badge",
    "settlement_oval",
    "army_stack",
    "ship",
)

ARMY_LIKE = frozenset({"army_stack"})
SHIP_LIKE = frozenset({"ship"})
SETTLEMENT_LIKE = frozenset({"settlement_badge", "settlement_oval"})


@dataclass(frozen=True)
class Detection:
    label: str
    score: float
    box_xyxy: tuple[float, float, float, float]
    #: Original image size reported by AO (optional).
    image_width: int | None = None
    image_height: int | None = None

    @property
    def cx(self) -> float:
        x1, _, x2, _ = self.box_xyxy
        return (x1 + x2) / 2.0

    @property
    def cy(self) -> float:
        _, y1, _, y2 = self.box_xyxy
        return (y1 + y2) / 2.0

    def centre_px(self) -> tuple[int, int]:
        return (int(round(self.cx)), int(round(self.cy)))

    def centre_norm(self, width: int, height: int) -> tuple[float, float]:
        if width <= 0 or height <= 0:
            raise ValueError("width/height must be positive")
        return (self.cx / float(width), self.cy / float(height))


@dataclass(frozen=True)
class DetectionResult:
    detections: list[Detection]
    image_width: int | None = None
    image_height: int | None = None
    inference_ms: float | None = None
    provider_id: str = ""
    raw_text: str = ""


def parse_detection_payload(raw: str | dict[str, Any] | None) -> DetectionResult:
    """Parse AO detection JSON (object or fenced) into ``DetectionResult``."""
    if raw is None:
        return DetectionResult(detections=[])
    if isinstance(raw, dict):
        obj = raw
        raw_text = json.dumps(raw)
    else:
        raw_text = str(raw).strip()
        if not raw_text:
            return DetectionResult(detections=[], raw_text="")
        obj = _loads_json_object(raw_text)
        if obj is None:
            return DetectionResult(detections=[], raw_text=raw_text)

    img = obj.get("image") if isinstance(obj.get("image"), dict) else {}
    model = obj.get("model") if isinstance(obj.get("model"), dict) else {}
    iw = _as_int(img.get("width"))
    ih = _as_int(img.get("height"))
    dets_raw = obj.get("detections")
    if not isinstance(dets_raw, list):
        return DetectionResult(
            detections=[],
            image_width=iw,
            image_height=ih,
            inference_ms=_as_float(model.get("inference_ms")),
            provider_id=str(model.get("provider_id") or ""),
            raw_text=raw_text,
        )

    out: list[Detection] = []
    for row in dets_raw:
        det = _parse_one(row, iw, ih)
        if det is not None:
            out.append(det)
    return DetectionResult(
        detections=out,
        image_width=iw,
        image_height=ih,
        inference_ms=_as_float(model.get("inference_ms")),
        provider_id=str(model.get("provider_id") or ""),
        raw_text=raw_text,
    )


def filter_labels(
    detections: Sequence[Detection],
    labels: Sequence[str] | frozenset[str],
    *,
    min_score: float = 0.0,
) -> list[Detection]:
    allow = {str(x) for x in labels}
    return [
        d
        for d in detections
        if d.label in allow and d.score >= float(min_score)
    ]


def nearest(
    detections: Sequence[Detection],
    *,
    x: float,
    y: float,
    pixel_space: bool = True,
) -> Detection | None:
    """Return detection whose centre is closest to ``(x, y)``."""
    if not detections:
        return None
    best: Detection | None = None
    best_d = float("inf")
    for d in detections:
        if pixel_space:
            cx, cy = d.cx, d.cy
        else:
            if not d.image_width or not d.image_height:
                continue
            cx, cy = d.centre_norm(d.image_width, d.image_height)
        dist = math.hypot(cx - x, cy - y)
        if dist < best_d:
            best_d = dist
            best = d
    return best


def pair_badge_to_oval(
    badges: Sequence[Detection],
    ovals: Sequence[Detection],
    *,
    max_dist_px: float = 80.0,
) -> list[tuple[Detection, Detection | None]]:
    """Greedy nearest oval under each badge (for settlement eval / click)."""
    remaining = list(ovals)
    pairs: list[tuple[Detection, Detection | None]] = []
    for badge in badges:
        if not remaining:
            pairs.append((badge, None))
            continue
        hit = nearest(remaining, x=badge.cx, y=badge.cy, pixel_space=True)
        if hit is None or math.hypot(hit.cx - badge.cx, hit.cy - badge.cy) > max_dist_px:
            pairs.append((badge, None))
            continue
        remaining.remove(hit)
        pairs.append((badge, hit))
    return pairs


def _parse_one(row: Any, iw: int | None, ih: int | None) -> Detection | None:
    if not isinstance(row, dict):
        return None
    label = str(row.get("label") or row.get("class") or "").strip()
    if not label:
        return None
    try:
        score = float(row.get("score") if row.get("score") is not None else row.get("confidence") or 0.0)
    except (TypeError, ValueError):
        score = 0.0
    box = row.get("box_xyxy") or row.get("bbox") or row.get("box")
    if not isinstance(box, (list, tuple)) or len(box) < 4:
        return None
    try:
        x1, y1, x2, y2 = (float(box[0]), float(box[1]), float(box[2]), float(box[3]))
    except (TypeError, ValueError):
        return None
    if x2 < x1:
        x1, x2 = x2, x1
    if y2 < y1:
        y1, y2 = y2, y1
    return Detection(
        label=label,
        score=score,
        box_xyxy=(x1, y1, x2, y2),
        image_width=iw,
        image_height=ih,
    )


def _loads_json_object(text: str) -> dict[str, Any] | None:
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        try:
            obj = json.loads(fence.group(1))
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            obj = json.loads(text[start : end + 1])
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _as_int(v: Any) -> int | None:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _as_float(v: Any) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


async def detect_campaign_frame(
    session: Any,
    *,
    images: list[dict[str, Any]],
    question_id: str,
    agent_provider_id: str | None = None,
    timeout: float | None = None,
    raise_errors: bool = False,
) -> DetectionResult:
    """Reach object_detection → parsed ``DetectionResult``."""
    from comstar_game_ai.agent.reach.director import call_map_object_detection

    raw = await call_map_object_detection(
        session,
        images=images,
        question_id=question_id,
        agent_provider_id=agent_provider_id,
        timeout=timeout,
        raise_errors=raise_errors,
    )
    return parse_detection_payload(raw)


def armies_and_ships(
    result: DetectionResult,
    *,
    include_ships: bool = True,
    min_score: float = 0.0,
) -> list[Detection]:
    labels = set(ARMY_LIKE)
    if include_ships:
        labels |= set(SHIP_LIKE)
    return filter_labels(result.detections, labels, min_score=min_score)
