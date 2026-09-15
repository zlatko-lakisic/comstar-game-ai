"""Read settlement plaques on a campaign screenshot (view-first, no Lists/seed).

Vision reports names / regions / owner colours only — never click coordinates.
In-frame badge centres come from ``settlement_detector`` (see
``docs/settlement-detector-handoff.md``). Off-screen locations stay on the
map-window projection path. Live Phase 2 must call through the deliberator's
Reach session — a second session on top of the director returns empty answers.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Literal

if TYPE_CHECKING:
    from PIL import Image

_LOGGER = logging.getLogger(__name__)

ViewStanding = Literal["rebel", "at_war", "neutral", "ally", "ours", "unknown"]

#: Attack tiers — exhaust an earlier tier before any later one.
_STANDING_ATTACK_RANK: dict[str, int] = {
    "rebel": 0,
    "at_war": 1,
    "neutral": 2,
    "ally": 3,
    "unknown": 4,
}


@dataclass(frozen=True)
class MapTargetHit:
    found: bool
    label: str
    x_norm: float | None = None
    y_norm: float | None = None
    confidence: float = 0.0
    reason: str = ""
    standing: ViewStanding = "unknown"
    region: str = ""
    colour: str = ""

    @property
    def click_norm(self) -> tuple[float, float] | None:
        if not self.found or self.x_norm is None or self.y_norm is None:
            return None
        return (float(self.x_norm), float(self.y_norm))


@dataclass(frozen=True)
class SettlementViewHit:
    """One settlement plaque visible on the current campaign frame.

    ``x_norm`` / ``y_norm`` are filled by the CV badge detector (or tests), never
    by the vision model contract.
    """

    label: str
    x_norm: float | None = None
    y_norm: float | None = None
    standing: ViewStanding = "unknown"
    confidence: float = 0.0
    reason: str = ""
    region: str = ""
    colour: str = ""

    @property
    def click_norm(self) -> tuple[float, float] | None:
        if self.x_norm is None or self.y_norm is None:
            return None
        return (float(self.x_norm), float(self.y_norm))

    def as_map_target(self) -> MapTargetHit:
        return MapTargetHit(
            found=True,
            label=self.label,
            x_norm=self.x_norm,
            y_norm=self.y_norm,
            confidence=self.confidence,
            reason=self.reason or "view_scan",
            standing=self.standing,
            region=self.region,
            colour=self.colour,
        )


def map_target_vision_schema() -> dict[str, Any]:
    """JSON schema for plaque reading (no click coordinates)."""
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["found", "label", "reason"],
        "properties": {
            "found": {"type": "boolean"},
            "label": {"type": "string"},
            "region": {"type": "string"},
            "colour": {"type": "string"},
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "standing": {
                "type": "string",
                "enum": ["rebel", "at_war", "neutral", "ally", "ours", "unknown"],
            },
            "reason": {"type": "string"},
        },
    }


def build_map_target_prompt(
    *,
    label: str,
    hint_quadrant: str = "",
) -> str:
    """Ask the vision model whether a named settlement plaque is visible."""
    name = (label or "").strip() or "the target settlement"
    hint = ""
    if hint_quadrant:
        hint = (
            f" The target is expected toward the {hint_quadrant} of the framed map "
            "(after the selected army was centred)."
        )
    return (
        "Reply with ONLY one JSON object. No prose, no markdown, no code fences.\n"
        "You are looking at a Total War: ROME REMASTERED campaign map screenshot.\n"
        f"Find the settlement named '{name}' on the open map.\n"
        "A settlement is marked by a plaque (pale cream lozenge with a round "
        "coloured badge on its left, name in large capitals, region below) "
        "and/or a town (orange-roofed buildings on a dark oval). "
        "Skip army banners beside walking figures.\n"
        "Report whether it is visible and the plaque colour if readable. "
        "Do NOT report coordinates or click points.\n"
        "Also report standing from the town/army banner relative to the player: "
        "rebel, at_war, neutral, ally, ours, or unknown.\n"
        f"{hint}"
        "Describe THIS image. Never copy wording or numbers from the examples.\n"
        "Shape: "
        '{"found":true|false,"label":"' + name + '","region":"name or unknown",'
        '"colour":"one word or unknown","confidence":0.00,'
        '"standing":"rebel|at_war|neutral|ally|ours|unknown","reason":"few words"}\n'
        "If not visible: found=false."
    )


def settlement_scan_schema() -> dict[str, Any]:
    """JSON schema for a multi-settlement plaque scan (no click coordinates)."""
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["settlements"],
        "properties": {
            "settlements": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["label", "colour"],
                    "properties": {
                        "label": {"type": "string"},
                        "region": {"type": "string"},
                        "colour": {"type": "string"},
                        "standing": {
                            "type": "string",
                            "enum": ["rebel", "at_war", "neutral", "ally", "ours", "unknown"],
                        },
                        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        "reason": {"type": "string"},
                    },
                },
            },
            "reason": {"type": "string"},
        },
    }


def build_settlement_scan_prompt(*, prefer_label: str = "") -> str:
    """Ask vision to list every settlement plaque readable in the frame."""
    prefer = (prefer_label or "").strip()
    prefer_line = ""
    if prefer:
        prefer_line = (
            f" If '{prefer}' is visible, include it; still list every other "
            "settlement too.\n"
        )
    return (
        "Reply with ONLY one JSON object. No prose, no markdown, no code fences.\n"
        "You are looking at a Total War: ROME REMASTERED campaign map screenshot.\n"
        "List every settlement plaque visible on the OPEN campaign map (not the "
        "minimap, not Lists, not UI chrome).\n"
        "A plaque is a pale cream lozenge with a round coloured badge on its left, "
        "settlement name in large capitals, region in smaller capitals below. "
        "A town alone (orange roofs on a dark oval) without a plaque may still "
        "count if the banner colour is readable — label it unknown.\n"
        "Skip army banners beside walking figures.\n"
        "For each settlement:\n"
        "- label: nameplate text if readable, else \"unknown\"\n"
        "- region: smaller capitals below the name, else \"unknown\"\n"
        "- colour: one word for the round badge (or town banner) colour\n"
        "- standing from the town banner (or garrison army banner if it replaced "
        "the town banner) relative to the PLAYER faction shown in the UI:\n"
        "  rebel = rebel / slave / grey independent\n"
        "  at_war = enemy / hostile / already at war\n"
        "  neutral = not allied, not at war\n"
        "  ally = allied faction (other Roman houses count as ally)\n"
        "  ours = player-owned settlement\n"
        "  unknown = cannot tell from the banner\n"
        "Do NOT report coordinates, click points, x, y, x_norm, or y_norm.\n"
        f"{prefer_line}"
        "Describe THIS image. Never copy wording or numbers from the skeleton.\n"
        "Shape: "
        '{"settlements":[{"label":"name","region":"name or unknown",'
        '"colour":"one word","standing":"rebel|at_war|neutral|ally|ours|unknown",'
        '"confidence":0.00,"reason":"few words"}],"reason":"few words"}\n'
        "Omit settlements you cannot see. Use [] if none. JSON only."
    )


def build_settlement_scan_reask_prompt() -> str:
    """Second-chance prompt when the model answered in prose."""
    return (
        "Previous answer was not valid JSON. "
        "Describe THIS image only. Never copy example wording.\n"
        "Reply with ONLY:\n"
        '{"settlements":[{"label":"name","region":"unknown","colour":"red",'
        '"standing":"ours","confidence":0.00,"reason":"few words"}],'
        '"reason":"few words"}\n'
        "standing must be one of: rebel, at_war, neutral, ally, ours, unknown. "
        "Do not include coordinates. JSON only."
    )


def normalize_view_standing(raw: str | None) -> ViewStanding:
    text = str(raw or "").strip().lower().replace(" ", "_").replace("-", "_")
    if text in {"rebel", "rebels", "slave"}:
        return "rebel"
    if text in {"at_war", "war", "enemy", "hostile", "enemies"}:
        return "at_war"
    if text in {"neutral", "peace", "non_aligned", "nonaligned"}:
        return "neutral"
    if text in {"ally", "allied", "alliance", "friend", "friendly"}:
        return "ally"
    if text in {"ours", "own", "owned", "player", "self", "julii", "romans_julii"}:
        return "ours"
    return "unknown"


def parse_settlement_scan(raw: str) -> list[SettlementViewHit]:
    """Parse a multi-settlement scan answer into view hits."""
    text = (raw or "").strip()
    if not text:
        return []
    payload: dict[str, Any] | None = None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        match = _JSON_OBJECT.search(text)
        if match:
            try:
                payload = json.loads(match.group(0))
            except json.JSONDecodeError:
                return []
    if not isinstance(payload, dict):
        return []

    rows = payload.get("settlements")
    if not isinstance(rows, list):
        return []

    hits: list[SettlementViewHit] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        label = str(row.get("label") or row.get("name") or "").strip()
        if not label:
            continue
        # Model contract must not emit click coordinates (S2). Ignore legacy
        # x/y fields if a stale answer still contains them.
        try:
            confidence = float(row.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        hits.append(
            SettlementViewHit(
                label=label,
                x_norm=None,
                y_norm=None,
                standing=normalize_view_standing(str(row.get("standing") or "")),
                confidence=max(0.0, min(1.0, confidence)),
                reason=str(row.get("reason") or "").strip(),
                region=str(row.get("region") or "").strip(),
                colour=str(row.get("colour") or row.get("color") or "").strip().lower(),
            )
        )
    return hits


def rank_attackable_settlements(
    hits: list[SettlementViewHit],
    *,
    prefer_label: str = "",
) -> list[SettlementViewHit]:
    """Order attack candidates by tier; exhaust each tier before the next.

    Tier order: rebel → enemy (at_war) → neutral → ally → unknown; skip ours.
    Among equals prefer ``prefer_label`` match, then higher confidence.
    """
    prefer = (prefer_label or "").strip().lower()

    def _key(hit: SettlementViewHit) -> tuple[int, int, float, str]:
        standing_rank = _STANDING_ATTACK_RANK.get(hit.standing, 4)
        label_l = hit.label.strip().lower()
        prefer_rank = 0
        if prefer:
            if label_l == prefer or prefer in label_l or label_l in prefer:
                prefer_rank = -1
        return (standing_rank, prefer_rank, -float(hit.confidence), label_l)

    return sorted(
        (h for h in hits if h.standing != "ours"),
        key=_key,
    )


def bearing_quadrant(*, from_x: float, from_y: float, to_x: float, to_y: float) -> str:
    """Coarse screen-facing hint from map coords (map Y north → screen up)."""
    dx = float(to_x) - float(from_x)
    dy = float(to_y) - float(from_y)  # map north positive
    # Screen: east = right, north = up → screen dy negative when map dy positive.
    sx, sy = dx, -dy
    if abs(sx) < 1e-6 and abs(sy) < 1e-6:
        return ""
    parts: list[str] = []
    if sy < -0.5:
        parts.append("top")
    elif sy > 0.5:
        parts.append("bottom")
    if sx < -0.5:
        parts.append("left")
    elif sx > 0.5:
        parts.append("right")
    if not parts:
        if abs(sx) >= abs(sy):
            parts.append("left" if sx < 0 else "right")
        else:
            parts.append("top" if sy < 0 else "bottom")
    return "-".join(parts) if len(parts) > 1 else parts[0]


_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


def parse_map_target_result(raw: str, *, expected_label: str = "") -> MapTargetHit | None:
    """Parse a map-target vision answer; None when unusable."""
    text = (raw or "").strip()
    if not text:
        return None
    payload: dict[str, Any] | None = None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        match = _JSON_OBJECT.search(text)
        if match:
            try:
                payload = json.loads(match.group(0))
            except json.JSONDecodeError:
                return None
    if not isinstance(payload, dict):
        return None

    label = str(payload.get("label") or expected_label or "").strip()
    found = bool(payload.get("found"))
    reason = str(payload.get("reason") or "").strip()
    try:
        confidence = float(payload.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    x_norm = y_norm = None
    # Ignore any coordinate fields — model contract must not emit them (S2).
    standing = normalize_view_standing(str(payload.get("standing") or ""))
    return MapTargetHit(
        found=found,
        label=label or expected_label,
        x_norm=x_norm,
        y_norm=y_norm,
        confidence=confidence,
        reason=reason or ("found" if found else "not_found"),
        standing=standing,
        region=str(payload.get("region") or "").strip(),
        colour=str(payload.get("colour") or payload.get("color") or "").strip().lower(),
    )


def locate_from_manifest(
    *,
    fixture_name: str,
    label: str,
    manifest: dict[str, Any],
    min_confidence: float = 0.55,
) -> MapTargetHit:
    """Oracle used by offline e2e tests — annotated click from the fixture manifest."""
    entry = manifest.get(fixture_name) or {}
    expected = str(entry.get("label") or "").strip().lower()
    want = label.strip().lower()
    if expected and want and expected != want and want not in expected:
        return MapTargetHit(
            found=False, label=label, confidence=0.0, reason="label_mismatch"
        )
    try:
        x = float(entry["x_norm"])
        y = float(entry["y_norm"])
    except (KeyError, TypeError, ValueError):
        return MapTargetHit(
            found=False, label=label, confidence=0.0, reason="manifest_incomplete"
        )
    return MapTargetHit(
        found=True,
        label=str(entry.get("label") or label),
        x_norm=x,
        y_norm=y,
        confidence=max(min_confidence, 0.9),
        reason="manifest_oracle",
    )


def query_map_target_sync(
    *,
    image: Image.Image,
    label: str,
    hint_quadrant: str = "",
    timeout_s: float = 600.0,
    on_heartbeat: Callable[[], None] | None = None,
) -> MapTargetHit | None:
    """Blocking Ada call with its own Reach session (standalone / tests only).

    Live Phase 2 must use ``SyncCampaignDeliberator.query_map_target`` instead so
    it does not open a second Reach session on top of the director.
    """
    import asyncio
    import concurrent.futures
    import time

    from comstar_game_ai.agent.reach.session import ReachSession

    def _status_print(status: object) -> None:
        phase = getattr(status, "phase", None) or str(status)
        print(f"MARCH vision status: {phase}", flush=True)

    async def _run() -> MapTargetHit | None:
        session = ReachSession(enable_game_query=False)
        try:
            await session.start()
            return await query_map_target_on_session(
                session,
                image=image,
                label=label,
                hint_quadrant=hint_quadrant,
                timeout_s=timeout_s,
                on_status=_status_print,
            )
        finally:
            await session.stop(clear_remote=False)

    ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        future = ex.submit(asyncio.run, _run())
        deadline = time.time() + float(timeout_s) + 5.0
        while True:
            if on_heartbeat is not None:
                try:
                    on_heartbeat()
                except Exception:  # noqa: BLE001
                    _LOGGER.debug("map-target heartbeat failed", exc_info=True)
            remaining = deadline - time.time()
            if remaining <= 0:
                future.cancel()
                _LOGGER.warning("map-target vision abort after %.0fs safety net", timeout_s)
                return None
            try:
                return future.result(timeout=min(2.0, remaining))
            except concurrent.futures.TimeoutError:
                continue
    except Exception:  # noqa: BLE001
        _LOGGER.warning("map-target vision failed", exc_info=True)
        return None
    finally:
        ex.shutdown(wait=False)


async def query_map_target_on_session(
    session: Any,
    *,
    image: Image.Image,
    label: str,
    hint_quadrant: str = "",
    timeout_s: float = 600.0,
    on_status: Callable[[object], None] | None = None,
) -> MapTargetHit | None:
    """Map-target locate on an already-started Reach session."""
    from comstar_game_ai.agent.compositor.views import ViewBudget, compose_reach_images
    from comstar_game_ai.agent.reach.director import call_map_target_vision

    display_label = (label or "").strip()
    if display_label and display_label == display_label.lower():
        display_label = display_label[:1].upper() + display_label[1:]

    prompt = build_map_target_prompt(label=display_label or label, hint_quadrant=hint_quadrant)

    def _default_status(status: object) -> None:
        phase = getattr(status, "phase", None) or str(status)
        print(f"MARCH vision status: {phase}", flush=True)

    images, _ = compose_reach_images(
        [image],
        budget=ViewBudget(max_images=1, width=1280, height=720, jpeg_quality=85),
    )
    if not images:
        _LOGGER.warning("map-target vision: compose produced no images")
        return None

    raw = await call_map_target_vision(
        session,
        text=prompt,
        question_id=f"map-target-{(label or 'x').lower().replace(' ', '-')[:24]}",
        images=images,
        timeout=timeout_s,
        on_status=on_status or _default_status,
    )
    hit = parse_map_target_result(raw, expected_label=label)
    if hit is None:
        preview = (raw or "").replace("\n", " ")[:240]
        _LOGGER.warning(
            "map-target vision unparseable for %r raw=%r",
            label,
            preview or "<empty>",
        )
        if preview:
            print(
                f"MARCH vision: unparseable for {label!r} raw={preview!r}",
                flush=True,
            )
        else:
            print(f"MARCH vision: empty answer for {label!r}", flush=True)
        _save_miss_frame(image, label)
    elif not hit.found:
        _LOGGER.info("map-target vision miss for %s: %s", label, hit.reason)
        _save_miss_frame(image, label)
    return hit


def _save_miss_frame(image: Image.Image, label: str) -> None:
    """Keep the frame that Ada could not locate, for offline diagnosis."""
    try:
        from pathlib import Path
        import time as _time

        out_dir = Path("data/runtime/map_target_misses")
        out_dir.mkdir(parents=True, exist_ok=True)
        safe = "".join(c if c.isalnum() else "_" for c in (label or "target"))[:32]
        stamp = _time.strftime("%Y%m%d-%H%M%S")
        path = out_dir / f"{stamp}_{safe}.jpg"
        image.convert("RGB").save(path, format="JPEG", quality=85)
        print(f"MARCH vision: saved miss frame {path}", flush=True)
    except Exception:  # noqa: BLE001
        _LOGGER.debug("map-target miss frame save failed", exc_info=True)


async def query_settlement_scan_on_session(
    session: Any,
    *,
    image: Image.Image,
    prefer_label: str = "",
    timeout_s: float = 600.0,
    on_status: Callable[[object], None] | None = None,
) -> list[SettlementViewHit]:
    """Multi-settlement view scan on an already-started Reach session."""
    from comstar_game_ai.agent.compositor.views import ViewBudget, compose_reach_images
    from comstar_game_ai.agent.reach.director import call_map_target_vision

    prompt = build_settlement_scan_prompt(prefer_label=prefer_label)

    def _default_status(status: object) -> None:
        phase = getattr(status, "phase", None) or str(status)
        print(f"MARCH scan status: {phase}", flush=True)

    images, _ = compose_reach_images(
        [image],
        budget=ViewBudget(max_images=1, width=1280, height=720, jpeg_quality=85),
    )
    if not images:
        _LOGGER.warning("settlement scan: compose produced no images")
        return []

    qid = "settlement-scan"
    if prefer_label.strip():
        safe = prefer_label.lower().replace(" ", "-")[:20]
        qid = f"settlement-scan-{safe}"

    raw = await call_map_target_vision(
        session,
        text=prompt,
        question_id=qid,
        images=images,
        timeout=timeout_s,
        on_status=on_status or _default_status,
        json_schema=settlement_scan_schema(),
    )
    hits = parse_settlement_scan(raw)
    if not hits and (raw or "").strip():
        # llava often answers in prose despite schema; one JSON-only reask.
        preview = (raw or "").replace("\n", " ")[:240]
        print(f"MARCH scan: reask for JSON only (first={preview!r})", flush=True)
        raw = await call_map_target_vision(
            session,
            text=build_settlement_scan_reask_prompt(),
            question_id=f"{qid}-reask",
            images=images,
            timeout=timeout_s,
            on_status=on_status or _default_status,
            json_schema=settlement_scan_schema(),
        )
        hits = parse_settlement_scan(raw)
    if not hits:
        preview = (raw or "").replace("\n", " ")[:240]
        _LOGGER.warning("settlement scan empty/unparseable raw=%r", preview or "<empty>")
        print(f"MARCH scan: empty/unparseable raw={preview!r}", flush=True)
        _save_miss_frame(image, prefer_label or "scan")
    else:
        print(
            f"MARCH scan: {len(hits)} settlement(s) — "
            + ", ".join(f"{h.label}[{h.standing}]" for h in hits[:8]),
            flush=True,
        )
    return hits


def query_settlement_scan_sync(
    *,
    image: Image.Image,
    prefer_label: str = "",
    timeout_s: float = 600.0,
    on_heartbeat: Callable[[], None] | None = None,
) -> list[SettlementViewHit]:
    """Blocking scan with its own Reach session (standalone / accept scripts).

    Live Phase 2 must use ``SyncCampaignDeliberator.query_settlement_scan``.
    """
    import asyncio
    import concurrent.futures
    import time

    from comstar_game_ai.agent.reach.session import ReachSession

    def _status_print(status: object) -> None:
        phase = getattr(status, "phase", None) or str(status)
        print(f"MARCH scan status: {phase}", flush=True)

    async def _run() -> list[SettlementViewHit]:
        session = ReachSession(enable_game_query=False)
        try:
            await session.start()
            return await query_settlement_scan_on_session(
                session,
                image=image,
                prefer_label=prefer_label,
                timeout_s=timeout_s,
                on_status=_status_print,
            )
        finally:
            await session.stop(clear_remote=False)

    ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        future = ex.submit(asyncio.run, _run())
        deadline = time.time() + float(timeout_s) + 5.0
        while True:
            if on_heartbeat is not None:
                try:
                    on_heartbeat()
                except Exception:  # noqa: BLE001
                    _LOGGER.debug("settlement-scan heartbeat failed", exc_info=True)
            remaining = deadline - time.time()
            if remaining <= 0:
                future.cancel()
                _LOGGER.warning("settlement scan abort after %.0fs safety net", timeout_s)
                return []
            try:
                return future.result(timeout=min(2.0, remaining))
            except concurrent.futures.TimeoutError:
                continue
    except Exception:  # noqa: BLE001
        _LOGGER.warning("settlement scan failed", exc_info=True)
        return []
    finally:
        ex.shutdown(wait=False)
