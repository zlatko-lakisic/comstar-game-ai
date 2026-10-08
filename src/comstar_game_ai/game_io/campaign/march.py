"""Campaign map marches: select the ordered stack, project the destination, right-click.

Belief coordinates are map space; clicks are client norms for the *current* camera.
Primary path (default):

1. Lists → Military Forces → row → locate, verifying the framed army matches
   belief ``from_xy`` via the radar frustum (``ARMY_FRUSTUM_MATCH_MAP``)
2. Canonical pose reset; re-measure frustum centre as **live** ``from``
3. Near path (live dist ≤ ``NEAR_SETTLEMENT_MAP_DIST`` and on-viewport): army-anchor
   project → glyph → right-click. Else far path: radar-frame toward dest, re-calibrate
4. Belief ``own_order`` steps only when ``projection_consistent``

The console pane is readable. The logs stay empty. The live path uses the
stored homography from the calibration report. With no valid fit it does not run.

Legacy assumed-centre ``destination_norm`` probes remain behind
``allow_legacy_geometry`` (default off). Left-click on a nameplate selects the
town — a known atlas trap — so destination actuation is always right-click.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from comstar_game_ai.agent.belief.store import BeliefStore
from comstar_game_ai.game_io.campaign.camera_pose import CameraPoseDirector, camera_config
from comstar_game_ai.game_io.campaign.combat import (
    NEUTRAL_CURSOR_PROBE,
    CombatDirector,
    StackSelection,
    client_norm_to_screen,
    client_size,
    read_cursor_handle,
)
from comstar_game_ai.game_io.campaign.map_projection import (
    DEFAULT_ANCHOR_SCALE,
    NEAR_PROJECTION_BLENDS,
    belief_to_radar_norm,
    detect_radar_frustum_map_aabb,
    map_to_client,
    transform_from_army_anchor,
    transform_from_view_aabb,
)
from comstar_game_ai.game_io.campaign.map_target_vision import MapTargetHit, SettlementViewHit
from comstar_game_ai.game_io.campaign.ui_mode import grab_rgb_image

if TYPE_CHECKING:
    from PIL import Image

    from comstar_game_ai.game_io.campaign.map_projection import MapClientTransform
    from comstar_game_ai.game_io.input.send_input import SendInputController

_LOGGER = logging.getLogger(__name__)

#: First Military Forces rows measured for Julii (see test_campaign_combat_step).
#: Without OCR we try these in order until frustum / glyph gates pass.
DEFAULT_LISTS_ROWS: tuple[tuple[float, float], ...] = (
    (0.30, 0.415),
    (0.30, 0.455),
    (0.30, 0.495),
    (0.30, 0.535),
)

#: Legacy single-step size; prefer :func:`step_candidates` for live marches.
MARCH_STEP_NORM = 0.16

#: Within this map distance (live frustum centre → dest) the settlement is usually
#: still framed after locate. Live Arretium→Segesta was ~10–16 map units with a
#: false near click; keep this below that band. Identity match stays at 12.
NEAR_SETTLEMENT_MAP_DIST = 8.0

#: If army-anchor projects the dest farther than this from screen centre, treat
#: as off-frame and radar-jump even when the point is still inside the viewport.
NEAR_CLIENT_OFFSET_MAX = 0.12

#: Mid → short → long: nameplate distance first, then land, then long overshoot last.
#: Live Segesta nameplate sat near (0.22–0.24, 0.50–0.54) from a centred army.
NEAR_STEP_NORMS: tuple[float, ...] = (0.26, 0.28, 0.24, 0.22, 0.30, 0.20, 0.16, 0.34, 0.38)

#: Short → long: land pathing when the settlement is off-screen.
FAR_STEP_NORMS: tuple[float, ...] = (0.14, 0.18, 0.22, 0.26, 0.30)

#: Map Y increases north; client Y increases down. Flip when projecting.
MAP_Y_TO_SCREEN_SIGN = -1.0

#: Max map-space distance between radar-frustum centre and ordered belief ``from_xy``.
#: Was 22 — Arretium (~67.5) falsely matched stale Flavius (89,82). See
#: docs/phase2-false-march-20260911.md.
ARMY_FRUSTUM_MATCH_MAP = 12.0

#: After pose reset, frustum centre may shift slightly vs the post-locate measure.
POSE_FRUSTUM_DRIFT_MAP = 8.0

LocateTargetFn = Callable[["Image.Image", str], MapTargetHit | None]
ScanSettlementsFn = Callable[["Image.Image"], list[SettlementViewHit]]


@dataclass(frozen=True)
class MarchOutcome:
    ordered: bool
    reason: str
    unit_cards: int = 0
    click_norm: tuple[float, float] | None = None
    step_to: tuple[float, float] | None = None
    cursor_changed: bool = False
    vision_used: bool = False
    button: str = ""
    calib_mode: str = ""
    selected_character: str = ""
    #: Measured radar-frustum centre after locate/pose (live army map XY).
    live_from_xy: tuple[float, float] | None = None
    #: True when the order used live geometry (near with live from, or far/radar).
    #: Driver must not write ``own_order`` belief steps when False.
    projection_consistent: bool = False
    #: True when live_from_xy is safe to write into belief (frustum-verified select).
    belief_refresh_ok: bool = False
    #: True only after the post-click outcome check. Belief stays unchanged until then.
    outcome_confirmed: bool = False


@dataclass
class MarchDirector:
    """Mouse march for campaign armies. Dependencies injectable for tests."""

    hwnd: int | None = None
    controller: SendInputController | None = None
    capture: Callable[[], Image.Image | None] | None = None
    cursor_handle: Callable[[], int] = read_cursor_handle
    to_screen: Callable[[float, float], tuple[int, int] | None] | None = None
    sleep: Callable[[float], None] = time.sleep
    hover_dwell_s: float = 1.2
    order_settle_s: float = 3.0
    lists_rows: tuple[tuple[float, float], ...] = DEFAULT_LISTS_ROWS
    step_norm: float = MARCH_STEP_NORM
    on_heartbeat: Callable[[], None] | None = None
    locate_target: LocateTargetFn | None = None
    #: View-first settlement scan (no Lists / seed). Preferred for vision besiege.
    scan_settlements: ScanSettlementsFn | None = None
    map_vision_min_confidence: float = 0.55
    #: Primary path: radar frame → calibrate → project → right-click.
    use_map_projection: bool = True
    #: Assumed-centre bearing probes. Off once projection ships.
    allow_legacy_geometry: bool = False
    #: Client-norms per map unit for dest-anchor fallback after radar frame.
    #: Z7 default comes from ``DEFAULT_ANCHOR_SCALE`` (0.0133 @ N=14).
    anchor_scale: float | None = None
    #: Optional annotated miss/hit frame directory (runtime only).
    debug_frame_dir: str | Path | None = None
    #: Override for tests; default reads live GetClientRect via :func:`client_size`.
    window_size: Callable[[], tuple[int, int] | None] | None = None
    #: When True (default), reset+verify canonical camera pose before projecting.
    require_canonical_pose: bool = True
    #: Part B: oval vision + sword + war-Yes after army select (skips projection).
    #: Default off (Z9) until map_target_vision returns reliable structured output.
    use_vision_besiege: bool = False
    allow_region_pan: bool = False
    belief: BeliefStore | None = None
    #: Stored homography. None loads the published report, which is invalid until step 2.
    map_fit: object | None = None
    #: ``show_cursorstat`` read. None grabs whatever is already on the frame.
    read_map: Callable[[], tuple[int, int] | None] | None = None
    #: Return ``move``, ``sword``, ``none``, or ``ambiguous``. None uses the handles below.
    cursor_role: Callable[[int], str] | None = None
    move_cursor_handle: int | None = None
    sword_cursor_handle: int | None = None
    #: Post-click check. None compares the radar frustum before and after.
    confirm_moved: Callable[[], bool] | None = None
    last_reason: str = field(default="", init=False)
    _combat: CombatDirector | None = field(default=None, init=False, repr=False)
    _pose: CameraPoseDirector | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.anchor_scale is None and DEFAULT_ANCHOR_SCALE is not None:
            self.anchor_scale = DEFAULT_ANCHOR_SCALE

    def _require_anchor_scale(self) -> float | None:
        if self.anchor_scale is None:
            return None
        return float(self.anchor_scale)

    def _client_size_label(self) -> str:
        size: tuple[int, int] | None = None
        if self.window_size is not None:
            size = self.window_size()
        elif self.hwnd is not None:
            size = client_size(self.hwnd)
        if size is None or size[0] <= 0 or size[1] <= 0:
            return "unknown"
        return f"{size[0]}x{size[1]}"

    def _combat_director(self) -> CombatDirector:
        if self._combat is None:
            self._combat = CombatDirector(
                hwnd=self.hwnd,
                controller=self.controller,
                capture=self.capture,
                cursor_handle=self.cursor_handle,
                to_screen=self.to_screen,
                sleep=self.sleep,
                hover_dwell_s=self.hover_dwell_s,
                order_settle_s=self.order_settle_s,
                on_heartbeat=self.on_heartbeat,
            )
        return self._combat

    def _pose_director(self) -> CameraPoseDirector:
        if self._pose is None:
            self._pose = CameraPoseDirector(
                hwnd=self.hwnd,
                controller=self.controller,
                capture=self._grab,
                sleep=self.sleep,
                army_match_map=ARMY_FRUSTUM_MATCH_MAP,
            )
        return self._pose

    def _ensure_canonical_pose(
        self, *, from_xy: tuple[float, float] | None, already_located: bool
    ) -> MarchOutcome | None:
        """Reset+verify pose. Returns a refusal outcome, or None when ok to project."""
        if not self.require_canonical_pose:
            return None
        # Centre check only after locate — before locate the frustum is elsewhere.
        centre_xy = from_xy if already_located else None
        result = self._pose_director().ensure_canonical(
            from_xy=centre_xy, already_located=already_located
        )
        self._note_fit("camera_move")
        self._note_fit("zoom")
        self._note_fit("recenter")
        if not result.ok:
            detail = ",".join(result.failed_checks) or result.reason
            measured = result.measured
            if measured is not None:
                print(
                    f"MARCH refused: pose_unverified checks=[{detail}] "
                    f"aabb_w={measured.width:.1f} aabb_h={measured.height:.1f} "
                    f"aspect={measured.aspect:.3f} expected_w={result.expected_width}",
                    flush=True,
                )
            return self._refuse(f"pose_unverified:{detail}")

        # Z3 surface gate — separate from AABB pose verify.
        from comstar_game_ai.game_io.campaign.map_surface import check_map_surface

        frame = self._grab()
        if frame is not None:
            surface = check_map_surface(frame)
            print(f"MARCH surface: {surface.as_log_dict()}", flush=True)
            if surface.is_map_overlay:
                return self._refuse("wrong_surface:map_overlay")

        # Derive scale from the verified frustum when unset (feeds the march; Z7
        # commits the number only after the order lands).
        if self._require_anchor_scale() is None and result.measured is not None:
            from comstar_game_ai.game_io.campaign.map_projection import (
                DEFAULT_VIEWPORT_BOUNDS,
            )

            x0, _y0, x1, _y1 = DEFAULT_VIEWPORT_BOUNDS
            viewport_w = float(x1 - x0)
            aabb_w = max(result.measured.width, 1e-3)
            derived = viewport_w / aabb_w
            self.anchor_scale = derived
            print(
                f"MARCH scale: derived={derived:.4f} from aabb_w={aabb_w:.1f} "
                f"viewport_w={viewport_w:.2f} (uncommitted until order lands)",
                flush=True,
            )
        return None

    def _heartbeat(self) -> None:
        if self.on_heartbeat is None:
            return
        try:
            self.on_heartbeat()
        except Exception:  # noqa: BLE001
            _LOGGER.warning("march heartbeat failed", exc_info=True)

    def _grab(self) -> Image.Image | None:
        if self.capture is not None:
            return self.capture()
        return grab_rgb_image(self.hwnd)

    def _screen(self, point: tuple[float, float]) -> tuple[int, int] | None:
        if self.to_screen is not None:
            return self.to_screen(*point)
        if self.hwnd is None:
            return None
        return client_norm_to_screen(self.hwnd, *point)

    def _click_norm(self, point: tuple[float, float]) -> bool:
        if self.controller is None or self.hwnd is None:
            return False
        return bool(self.controller.click_client_norm(self.hwnd, point[0], point[1], dwell_ms=60))

    def _hover(self, point: tuple[float, float]) -> bool:
        if self.controller is None:
            return False
        screen = self._screen(point)
        if screen is None:
            return False
        self.controller.move_mouse(*screen)
        self.sleep(0.15)
        self.controller.move_mouse(*screen)
        self.sleep(self.hover_dwell_s)
        return True

    def _lists_row_order(
        self, preferred_row: tuple[float, float] | None
    ) -> list[tuple[float, float]]:
        rows: list[tuple[float, float]] = []
        if preferred_row is not None:
            rows.append(preferred_row)
        rows.extend(self.lists_rows)
        seen: set[tuple[float, float]] = set()
        ordered: list[tuple[float, float]] = []
        for row in rows:
            if row in seen:
                continue
            seen.add(row)
            ordered.append(row)
        return ordered

    def acquire_any_stack(
        self, preferred_row: tuple[float, float] | None = None
    ) -> StackSelection | None:
        """Lists → Military Forces → locate until the HUD shows a selection."""
        combat = self._combat_director()
        for row in self._lists_row_order(preferred_row):
            self._heartbeat()
            selection = combat.acquire_stack(row)
            if selection.unit_cards >= 1:
                return selection
            _LOGGER.info("march: lists row %s did not select a stack (%s)", row, selection.reason)
        return None

    def _measure_frustum_centre(
        self, image: Image.Image | None = None
    ) -> tuple[float, float] | None:
        """Radar frustum centre in map space, or None when CV cannot decide."""
        frame = image if image is not None else self._grab()
        if frame is None:
            return None
        aabb = detect_radar_frustum_map_aabb(frame)
        if aabb is None:
            return None
        (min_x, min_y), (max_x, max_y) = aabb
        return (0.5 * (min_x + max_x), 0.5 * (min_y + max_y))

    def _frustum_matches_army(
        self, image: Image.Image, from_xy: tuple[float, float]
    ) -> bool | None:
        """True/False when frustum found; None when CV cannot decide."""
        centre = self._measure_frustum_centre(image)
        if centre is None:
            return None
        cx, cy = centre
        dist = math.hypot(cx - from_xy[0], cy - from_xy[1])
        ok = dist <= ARMY_FRUSTUM_MATCH_MAP
        _LOGGER.info(
            "march: frustum centre=(%.1f,%.1f) from=(%.1f,%.1f) dist=%.1f match=%s",
            cx,
            cy,
            from_xy[0],
            from_xy[1],
            dist,
            ok,
        )
        return ok

    def acquire_ordered_stack(
        self,
        *,
        from_x: float,
        from_y: float,
        preferred_row: tuple[float, float] | None = None,
        character_name: str = "",
    ) -> tuple[StackSelection, tuple[float, float], str, tuple[float, float] | None] | None:
        """Select a Military Forces row whose framed pose matches ``from_xy``.

        Returns ``(selection, lists_row, verify_mode, frustum_centre)`` or None.
        """
        combat = self._combat_director()
        from_xy = (float(from_x), float(from_y))
        unverified: list[
            tuple[StackSelection, tuple[float, float], tuple[float, float] | None]
        ] = []
        for row in self._lists_row_order(preferred_row):
            self._heartbeat()
            selection = combat.acquire_stack(row)
            if selection.unit_cards < 1:
                _LOGGER.info(
                    "march: lists row %s did not select a stack (%s)",
                    row,
                    selection.reason,
                )
                continue
            image = self._grab()
            centre = self._measure_frustum_centre(image) if image is not None else None
            if image is None:
                unverified.append((selection, row, centre))
                continue
            match = self._frustum_matches_army(image, from_xy)
            if match is False:
                print(
                    f"MARCH select: row {row} frustum ≠ {character_name or 'ordered army'} "
                    f"from=({from_x:.1f},{from_y:.1f}) — next row",
                    flush=True,
                )
                continue
            if match is True:
                print(
                    f"MARCH select: row {row} verified via frustum "
                    f"who={character_name or '-'} cards={selection.unit_cards}"
                    + (
                        f" centre=({centre[0]:.1f},{centre[1]:.1f})"
                        if centre is not None
                        else ""
                    ),
                    flush=True,
                )
                return selection, row, "frustum", centre
            unverified.append((selection, row, centre))

        if unverified:
            selection, row, centre = unverified[0]
            print(
                f"MARCH select: row {row} cards={selection.unit_cards} "
                f"frustum unavailable — tentative who={character_name or '-'}",
                flush=True,
            )
            return selection, row, "cards_unverified", centre
        return None

    def _frame_destination(self, to_x: float, to_y: float) -> bool:
        """Coarse radar jump so the destination belief point enters the viewport."""
        radar = belief_to_radar_norm((to_x, to_y))
        print(
            f"MARCH frame: radar click ({radar[0]:.3f},{radar[1]:.3f}) "
            f"for map=({to_x:.1f},{to_y:.1f})",
            flush=True,
        )
        if not self._click_norm(radar):
            return False
        self.sleep(1.2)
        self._heartbeat()
        # North-up so frustum / dest-anchor stay axis-aligned.
        if self.controller is not None and self.hwnd is not None:
            self.controller.tap_key("pageup", dwell_ms=40, hwnd=self.hwnd)
            self.sleep(0.35)
        return True

    def _calibrate_army_anchored(
        self, *, army_map_xy: tuple[float, float]
    ) -> tuple[MapClientTransform, str] | None:
        """North-up local transform after Lists-locate framed the army at centre."""
        scale = self._require_anchor_scale()
        if scale is None:
            return None
        if self.controller is not None and self.hwnd is not None:
            self.controller.tap_key("pageup", dwell_ms=40, hwnd=self.hwnd)
            self.sleep(0.25)
        transform = transform_from_army_anchor(
            army_map_xy=army_map_xy,
            scale=scale,
            map_y_to_screen_sign=MAP_Y_TO_SCREEN_SIGN,
        )
        print(
            f"MARCH calib: army_anchor scale={scale} "
            f"at map=({army_map_xy[0]:.1f},{army_map_xy[1]:.1f})",
            flush=True,
        )
        return transform, "army_anchor"

    def _calibrate_after_frame(
        self, *, dest_map_xy: tuple[float, float]
    ) -> tuple[MapClientTransform, str] | None:
        """Calibrate after a radar jump that should leave the destination near centre.

        Prefer dest-anchor when frustum AABB aims into the HUD or far from centre —
        live Flavius→Segesta frustum landed at y≈0.70 on empty grass / parchment.
        """
        image = self._grab()
        if image is not None:
            aabb = detect_radar_frustum_map_aabb(image)
            if aabb is not None:
                frustum = transform_from_view_aabb(map_min=aabb[0], map_max=aabb[1])
                if frustum is not None:
                    projected = map_to_client(frustum, dest_map_xy)
                    if projected is not None:
                        cx, cy = projected
                        near_centre = abs(cx - 0.50) < 0.18 and abs(cy - 0.48) < 0.18
                        if near_centre:
                            print(
                                f"MARCH calib: frustum ok near centre "
                                f"→ ({cx:.3f},{cy:.3f}) aabb={aabb}",
                                flush=True,
                            )
                            return frustum, "frustum"
                        print(
                            f"MARCH calib: frustum rejected "
                            f"projected=({cx:.3f},{cy:.3f}) aabb={aabb} — dest_anchor",
                            flush=True,
                        )
        scale = self._require_anchor_scale()
        if scale is None:
            return None
        transform = transform_from_army_anchor(
            army_map_xy=dest_map_xy,
            scale=scale,
            map_y_to_screen_sign=MAP_Y_TO_SCREEN_SIGN,
        )
        print(
            f"MARCH calib: dest_anchor scale={scale} "
            f"at map=({dest_map_xy[0]:.1f},{dest_map_xy[1]:.1f})",
            flush=True,
        )
        return transform, "dest_anchor"

    def _save_debug_frame(
        self,
        *,
        click: tuple[float, float],
        label: str,
        ok: bool,
    ) -> None:
        if not self.debug_frame_dir:
            return
        image = self._grab()
        if image is None:
            return
        try:
            from PIL import ImageDraw

            out = Path(self.debug_frame_dir)
            out.mkdir(parents=True, exist_ok=True)
            stamp = time.strftime("%Y%m%d-%H%M%S")
            path = out / f"{stamp}_{'hit' if ok else 'miss'}_{label or 'dest'}.jpg"
            draw = ImageDraw.Draw(image)
            w, h = image.size
            px, py = int(click[0] * w), int(click[1] * h)
            r = 8
            color = (40, 220, 80) if ok else (220, 40, 40)
            draw.ellipse((px - r, py - r, px + r, py + r), outline=color, width=3)
            draw.line((px - 12, py, px + 12, py), fill=color, width=2)
            draw.line((px, py - 12, px, py + 12), fill=color, width=2)
            image.save(path, quality=90)
            print(f"MARCH debug frame: {path}", flush=True)
        except Exception:  # noqa: BLE001
            _LOGGER.warning("march debug frame save failed", exc_info=True)

    @staticmethod
    def map_distance(*, from_x: float, from_y: float, to_x: float, to_y: float) -> float:
        return math.hypot(float(to_x) - float(from_x), float(to_y) - float(from_y))

    @staticmethod
    def step_candidates(map_dist: float) -> tuple[float, ...]:
        """Norm distances to try along the bearing, nearest-settlement first when close."""
        if map_dist <= NEAR_SETTLEMENT_MAP_DIST:
            return NEAR_STEP_NORMS
        return FAR_STEP_NORMS

    @staticmethod
    def destination_norm(
        *,
        from_x: float,
        from_y: float,
        to_x: float,
        to_y: float,
        step_norm: float = MARCH_STEP_NORM,
        origin: tuple[float, float] = (0.50, 0.48),
        map_y_to_screen_sign: float = MAP_Y_TO_SCREEN_SIGN,
    ) -> tuple[float, float] | None:
        packed = MarchDirector.destination_norm_ex(
            from_x=from_x,
            from_y=from_y,
            to_x=to_x,
            to_y=to_y,
            step_norm=step_norm,
            origin=origin,
            map_y_to_screen_sign=map_y_to_screen_sign,
        )
        return None if packed is None else packed[0]

    @staticmethod
    def destination_norm_ex(
        *,
        from_x: float,
        from_y: float,
        to_x: float,
        to_y: float,
        step_norm: float = MARCH_STEP_NORM,
        origin: tuple[float, float] = (0.50, 0.48),
        map_y_to_screen_sign: float = MAP_Y_TO_SCREEN_SIGN,
        x_bounds: tuple[float, float] = (0.15, 0.85),
        y_bounds: tuple[float, float] = (0.12, 0.78),
    ) -> tuple[tuple[float, float], bool] | None:
        """Like ``destination_norm``, plus whether the point hit a screen-edge clamp."""
        dx = float(to_x) - float(from_x)
        dy = float(to_y) - float(from_y)
        dist = math.hypot(dx, dy)
        if dist < 1e-6:
            return None
        ux, uy = dx / dist, dy / dist
        ox, oy = origin
        raw_x = ox + ux * float(step_norm)
        raw_y = oy + map_y_to_screen_sign * uy * float(step_norm)
        x = min(x_bounds[1], max(x_bounds[0], raw_x))
        y = min(y_bounds[1], max(y_bounds[0], raw_y))
        clamped = abs(x - raw_x) > 1e-9 or abs(y - raw_y) > 1e-9
        return (x, y), clamped

    @staticmethod
    def one_tile_step(
        *,
        from_x: float,
        from_y: float,
        to_x: float,
        to_y: float,
        tile: float = 1.0,
    ) -> tuple[float, float]:
        dx = float(to_x) - float(from_x)
        dy = float(to_y) - float(from_y)
        dist = math.hypot(dx, dy)
        if dist < 1e-6:
            return (float(from_x), float(from_y))
        scale = min(float(tile), dist) / dist
        return (float(from_x) + dx * scale, float(from_y) + dy * scale)

    def _try_vision_click(
        self,
        *,
        target_label: str,
        from_x: float,
        from_y: float,
        to_x: float,
        to_y: float,
        baseline: int,
        unit_cards: int,
        character_name: str,
    ) -> MarchOutcome | None:
        if self.locate_target is None:
            return None
        image = self._grab()
        if image is None:
            print("MARCH vision: no frame", flush=True)
            return None
        self._heartbeat()
        hit = self.locate_target(image, target_label)
        if hit is None or not hit.found or hit.click_norm is None:
            reason = getattr(hit, "reason", "miss") if hit is not None else "miss"
            print(f"MARCH vision: miss ({reason})", flush=True)
            _LOGGER.info("march: vision miss for %s (%s)", target_label, reason)
            return None
        if hit.confidence < self.map_vision_min_confidence:
            print(
                f"MARCH vision: confidence {hit.confidence:.2f} < "
                f"{self.map_vision_min_confidence:.2f} for {target_label!r}",
                flush=True,
            )
            return None
        click = hit.click_norm
        print(
            f"MARCH vision: hit ({click[0]:.3f},{click[1]:.3f}) "
            f"conf={hit.confidence:.2f} — hovering for glyph",
            flush=True,
        )
        if not self._hover(click):
            print("MARCH vision: hover failed", flush=True)
            return None
        hovered = self.cursor_handle()
        if hovered == 0 or hovered == baseline:
            print(
                f"MARCH vision: no cursor glyph at ({click[0]:.3f},{click[1]:.3f}) "
                "— projection/geometry fallback",
                flush=True,
            )
            return None
        return self._issue_click(
            click=click,
            from_x=from_x,
            from_y=from_y,
            to_x=to_x,
            to_y=to_y,
            unit_cards=unit_cards,
            character_name=character_name or target_label,
            cursor_changed=True,
            vision_used=True,
            calib_mode="vision",
        )

    def _issue_click(
        self,
        *,
        click: tuple[float, float],
        from_x: float,
        from_y: float,
        to_x: float,
        to_y: float,
        unit_cards: int,
        character_name: str,
        cursor_changed: bool,
        vision_used: bool,
        calib_mode: str = "",
        live_from_xy: tuple[float, float] | None = None,
        projection_consistent: bool = False,
        belief_refresh_ok: bool = False,
    ) -> MarchOutcome:
        if self.controller is None:
            return self._refuse(
                "no_controller",
                unit_cards,
                live_from_xy=live_from_xy,
                belief_refresh_ok=belief_refresh_ok,
            )
        screen = self._screen(click)
        if screen is None:
            return self._refuse(
                "no_screen_coords",
                unit_cards,
                live_from_xy=live_from_xy,
                belief_refresh_ok=belief_refresh_ok,
            )
        right = getattr(self.controller, "right_click", None)
        if callable(right):
            right(*screen, dwell_ms=120, settle_ms=450)
            button = "right"
        else:
            self.controller.click(*screen, dwell_ms=120, settle_ms=450)
            button = "left"
        self.sleep(self.order_settle_s)
        self._heartbeat()
        # Belief steps only when projection used live geometry (near with live
        # from, or far/radar). Stops own_order fiction toward Segesta from Arretium.
        step = None
        if projection_consistent:
            step = self.one_tile_step(from_x=from_x, from_y=from_y, to_x=to_x, to_y=to_y)
        who = character_name or "stack"
        self.last_reason = "ordered"
        self._save_debug_frame(click=click, label=who.replace(" ", "_"), ok=True)
        print(
            f"MARCH ordered click=({click[0]:.3f},{click[1]:.3f}) "
            f"button={button} cursor_changed={cursor_changed} vision={vision_used} "
            f"calib={calib_mode or '-'} who={who} cards={unit_cards} step={step} "
            f"projection_consistent={projection_consistent}",
            flush=True,
        )
        _LOGGER.info(
            "march ordered for %s click=(%.3f,%.3f) button=%s cursor_changed=%s "
            "vision=%s calib=%s step=%s cards=%s projection_consistent=%s",
            who,
            click[0],
            click[1],
            button,
            cursor_changed,
            vision_used,
            calib_mode,
            step,
            unit_cards,
            projection_consistent,
        )
        return MarchOutcome(
            ordered=True,
            reason="ordered",
            unit_cards=unit_cards,
            click_norm=click,
            step_to=step,
            cursor_changed=cursor_changed,
            vision_used=vision_used,
            button=button,
            calib_mode=calib_mode,
            selected_character=who,
            live_from_xy=live_from_xy,
            projection_consistent=projection_consistent,
            belief_refresh_ok=belief_refresh_ok,
        )

    def _note_fit(self, trigger: str) -> None:
        fit = self.map_fit
        note = getattr(fit, "note", None)
        if callable(note):
            note(trigger)

    def _keep_fit(self, fit: object) -> bool:
        """One-point check before a march. A miss or a UI read tries the next spare."""
        grid = tuple(getattr(fit, "grid", ()) or ())
        if not grid:
            return bool(getattr(fit, "valid", False))
        trigger = str(getattr(fit, "pending_trigger", "") or "pre_march")
        client = grid[0]
        read = None
        for spare in grid:
            if not self._hover(spare):
                continue
            read = self._read_map_xy()
            client = spare
            if read is not None:
                break
        decision = fit.one_point(client_xy=client, read_xy=read, trigger=trigger)
        if decision == "keep":
            return True
        fit.valid = False
        fit.log.append(
            {"event": "refit", "decision": "invalid", "reason": "probe_outside"}
        )
        return False

    def _current_fit(self):
        if self.map_fit is not None:
            return self.map_fit
        from comstar_game_ai.game_io.campaign.map_fit_runtime import load_fit_runtime

        self.map_fit = load_fit_runtime()
        return self.map_fit

    def _read_map_xy(self) -> tuple[int, int] | None:
        if self.read_map is not None:
            return self.read_map()
        frame = self._grab()
        if frame is None:
            return None
        from comstar_game_ai.game_io.campaign.console_cursorstat import (
            read_console_cursorstat,
        )

        return read_console_cursorstat(frame).xy

    def _role(self, baseline: int) -> str:
        if self.cursor_role is not None:
            return self.cursor_role(baseline)
        current = self.cursor_handle()
        if current == 0 or current == baseline:
            return "none"
        if self.move_cursor_handle is not None and current == self.move_cursor_handle:
            return "move"
        if self.sword_cursor_handle is not None and current == self.sword_cursor_handle:
            return "sword"
        return "ambiguous"

    def _march_closed_loop(
        self,
        *,
        from_x: float,
        from_y: float,
        to_x: float,
        to_y: float,
        lists_row: tuple[float, float] | None,
        character_name: str,
        target_label: str,
        selection: StackSelection,
        baseline: int,
        live_from_xy: tuple[float, float] | None = None,
        belief_refresh_ok: bool = False,
    ) -> MarchOutcome:
        """Aim with the homography, read the console, correct at most three times."""
        del lists_row, target_label
        fit = self._current_fit()
        homography = None if fit is None else fit.homography
        tolerance = 3.0 if fit is None or fit.tolerance is None else float(fit.tolerance)
        if homography is None:
            return self._refuse(
                "fit_invalid",
                selection.unit_cards,
                live_from_xy=live_from_xy,
                belief_refresh_ok=belief_refresh_ok,
            )
        target = (float(to_x), float(to_y))
        client = homography.map_to_client(target)
        if client is None:
            return self._refuse(
                "off_screen",
                selection.unit_cards,
                live_from_xy=live_from_xy,
                belief_refresh_ok=belief_refresh_ok,
            )
        for _attempt in range(3):
            if not self._hover(client):
                return self._refuse(
                    "hover_failed",
                    selection.unit_cards,
                    live_from_xy=live_from_xy,
                    belief_refresh_ok=belief_refresh_ok,
                )
            read = self._read_map_xy()
            if read is None:
                continue
            error = math.hypot(read[0] - target[0], read[1] - target[1])
            if error > tolerance:
                predicted = homography.client_to_map(client)
                if predicted is None:
                    break
                corrected = (
                    target[0] - (read[0] - predicted[0]),
                    target[1] - (read[1] - predicted[1]),
                )
                nxt = homography.map_to_client(corrected)
                if nxt is None:
                    break
                client = nxt
                continue
            role = self._role(baseline)
            if role != "move":
                return self._refuse(
                    f"glyph_{role}",
                    selection.unit_cards,
                    live_from_xy=live_from_xy,
                    belief_refresh_ok=belief_refresh_ok,
                )
            before = self._measure_frustum_centre()
            self._issue_click(
                click=client,
                from_x=from_x,
                from_y=from_y,
                to_x=to_x,
                to_y=to_y,
                unit_cards=selection.unit_cards,
                character_name=character_name,
                cursor_changed=True,
                vision_used=False,
                calib_mode="homography",
                live_from_xy=live_from_xy,
                projection_consistent=False,
                belief_refresh_ok=belief_refresh_ok,
            )
            confirmed = (
                self.confirm_moved()
                if self.confirm_moved is not None
                else self._frustum_advanced(before, target)
            )
            if not confirmed:
                return MarchOutcome(
                    ordered=False,
                    reason="outcome_unconfirmed",
                    unit_cards=selection.unit_cards,
                    click_norm=client,
                    live_from_xy=live_from_xy,
                    belief_refresh_ok=belief_refresh_ok,
                )
            step = self.one_tile_step(
                from_x=from_x, from_y=from_y, to_x=to_x, to_y=to_y
            )
            return MarchOutcome(
                ordered=True,
                reason="ordered",
                unit_cards=selection.unit_cards,
                click_norm=client,
                step_to=step,
                cursor_changed=True,
                button="right",
                calib_mode="homography",
                live_from_xy=live_from_xy,
                projection_consistent=True,
                belief_refresh_ok=belief_refresh_ok,
                outcome_confirmed=True,
            )
        return self._refuse(
            "not_converged",
            selection.unit_cards,
            live_from_xy=live_from_xy,
            belief_refresh_ok=belief_refresh_ok,
        )

    def _frustum_advanced(
        self,
        before: tuple[float, float] | None,
        target: tuple[float, float],
    ) -> bool:
        """True when the radar centre moved toward the target after the click."""
        after = self._measure_frustum_centre()
        if before is None or after is None:
            return False
        before_gap = math.hypot(before[0] - target[0], before[1] - target[1])
        after_gap = math.hypot(after[0] - target[0], after[1] - target[1])
        return after_gap + 0.5 < before_gap

    def _march_via_projection(
        self,
        *,
        from_x: float,
        from_y: float,
        to_x: float,
        to_y: float,
        lists_row: tuple[float, float] | None,
        character_name: str,
        target_label: str,
        selection: StackSelection,
        baseline: int,
        live_from_xy: tuple[float, float] | None = None,
        belief_refresh_ok: bool = False,
    ) -> MarchOutcome:
        dist = self.map_distance(from_x=from_x, from_y=from_y, to_x=to_x, to_y=to_y)
        transform: MapClientTransform | None = None
        calib_mode = ""
        used_far_path = False

        # Near targets: Lists-locate already framed the army. Project from that
        # pose — do not radar-jump (operator saw that minimap click; coarse frustum
        # then aimed into the HUD south of Segesta).
        if dist <= NEAR_SETTLEMENT_MAP_DIST:
            calibrated = self._calibrate_army_anchored(army_map_xy=(from_x, from_y))
            if calibrated is None:
                return self._refuse(
                    "anchor_scale_unset",
                    selection.unit_cards,
                    live_from_xy=live_from_xy,
                    belief_refresh_ok=belief_refresh_ok,
                )
            transform, calib_mode = calibrated
            click = map_to_client(transform, (to_x, to_y))
            if click is None:
                print(
                    "MARCH project: near target outside viewport after locate — "
                    "radar framing",
                    flush=True,
                )
                transform = None
            else:
                off = max(abs(click[0] - 0.50), abs(click[1] - 0.48))
                if off > NEAR_CLIENT_OFFSET_MAX:
                    print(
                        f"MARCH project: near target far from centre "
                        f"client=({click[0]:.3f},{click[1]:.3f}) off={off:.3f} — "
                        "radar framing",
                        flush=True,
                    )
                    transform = None

        if transform is None:
            used_far_path = True
            if not self._frame_destination(to_x, to_y):
                return self._refuse(
                    "radar_frame_failed", selection.unit_cards, live_from_xy=live_from_xy,
                    belief_refresh_ok=belief_refresh_ok,
                )
            # Re-select so the ordered army stays selected after the camera jump.
            acquired = self.acquire_ordered_stack(
                from_x=from_x,
                from_y=from_y,
                preferred_row=lists_row,
                character_name=character_name,
            )
            if acquired is None:
                return self._refuse(
                    "stack_not_selected_after_frame",
                    selection.unit_cards,
                    live_from_xy=live_from_xy,
                    belief_refresh_ok=belief_refresh_ok,
                )
            selection = acquired[0]
            calibrated = self._calibrate_after_frame(dest_map_xy=(to_x, to_y))
            if calibrated is None:
                return self._refuse(
                    "calibrate_failed", selection.unit_cards, live_from_xy=live_from_xy,
                    belief_refresh_ok=belief_refresh_ok,
                )
            transform, calib_mode = calibrated

        click = map_to_client(transform, (to_x, to_y))
        if click is None:
            scale = self._require_anchor_scale()
            if scale is None:
                return self._refuse(
                    "anchor_scale_unset", selection.unit_cards, live_from_xy=live_from_xy,
                    belief_refresh_ok=belief_refresh_ok,
                )
            transform = transform_from_army_anchor(
                army_map_xy=(to_x, to_y),
                scale=scale,
                map_y_to_screen_sign=MAP_Y_TO_SCREEN_SIGN,
            )
            calib_mode = "dest_anchor_retry"
            used_far_path = True
            click = map_to_client(transform, (to_x, to_y))
        if click is None:
            self._save_debug_frame(
                click=(0.5, 0.48),
                label=(target_label or character_name or "dest").replace(" ", "_"),
                ok=False,
            )
            return self._refuse(
                "projection_outside_viewport",
                selection.unit_cards,
                live_from_xy=live_from_xy,
                belief_refresh_ok=belief_refresh_ok,
            )

        near = dist <= NEAR_SETTLEMENT_MAP_DIST and not used_far_path
        # Consistent when we projected from live from on a true near path, or
        # completed the far/radar path toward the destination map point.
        projection_consistent = near or used_far_path
        candidates = self._projection_candidates(
            transform,
            from_x=from_x,
            from_y=from_y,
            to_x=to_x,
            to_y=to_y,
            near=near,
        )
        residual = getattr(transform, "residual_rms", 0.0)
        print(
            f"MARCH project: map=({to_x:.1f},{to_y:.1f}) → "
            f"client=({click[0]:.3f},{click[1]:.3f}) "
            f"calib={calib_mode} residual_rms={residual:.4f} "
            f"probes={len(candidates)} who={character_name or '-'} "
            f"far={used_far_path} consistent={projection_consistent}",
            flush=True,
        )

        # Optional vision confirmation after projection (not the primary locator).
        if self.locate_target is not None and target_label.strip():
            vision_outcome = self._try_vision_click(
                target_label=target_label,
                from_x=from_x,
                from_y=from_y,
                to_x=to_x,
                to_y=to_y,
                baseline=baseline,
                unit_cards=selection.unit_cards,
                character_name=character_name,
            )
            if vision_outcome is not None:
                # Re-wrap with live_from / consistency when vision orders.
                if vision_outcome.ordered:
                    return MarchOutcome(
                        ordered=True,
                        reason=vision_outcome.reason,
                        unit_cards=vision_outcome.unit_cards,
                        click_norm=vision_outcome.click_norm,
                        step_to=(
                            vision_outcome.step_to if projection_consistent else None
                        ),
                        cursor_changed=vision_outcome.cursor_changed,
                        vision_used=True,
                        button=vision_outcome.button,
                        calib_mode=vision_outcome.calib_mode or calib_mode,
                        selected_character=vision_outcome.selected_character,
                        live_from_xy=live_from_xy,
                        projection_consistent=projection_consistent,
                        belief_refresh_ok=belief_refresh_ok,
                    )
                return vision_outcome

        tried: list[str] = []
        for candidate in candidates:
            if not self._hover(candidate):
                tried.append(f"({candidate[0]:.3f},{candidate[1]:.3f}):hover_failed")
                continue
            hovered = self.cursor_handle()
            if hovered == 0:
                tried.append(f"({candidate[0]:.3f},{candidate[1]:.3f}):unreadable")
                continue
            if hovered == baseline:
                tried.append(f"({candidate[0]:.3f},{candidate[1]:.3f}):same")
                continue
            print(
                f"MARCH project: glyph at ({candidate[0]:.3f},{candidate[1]:.3f}) "
                f"(tried {'; '.join(tried) or 'primary'})",
                flush=True,
            )
            return self._issue_click(
                click=candidate,
                from_x=from_x,
                from_y=from_y,
                to_x=to_x,
                to_y=to_y,
                unit_cards=selection.unit_cards,
                character_name=character_name or target_label,
                cursor_changed=True,
                vision_used=False,
                calib_mode=calib_mode,
                live_from_xy=live_from_xy,
                projection_consistent=projection_consistent,
                belief_refresh_ok=belief_refresh_ok,
            )

        miss = candidates[0] if candidates else click
        self._save_debug_frame(
            click=miss,
            label=(target_label or character_name or "dest").replace(" ", "_"),
            ok=False,
        )
        print(
            f"MARCH project: no cursor glyph — tried {'; '.join(tried) or 'none'}",
            flush=True,
        )
        return self._refuse(
            "no_move_cursor", selection.unit_cards, live_from_xy=live_from_xy,
            belief_refresh_ok=belief_refresh_ok,
        )

    def _projection_candidates(
        self,
        transform: MapClientTransform,
        *,
        from_x: float,
        from_y: float,
        to_x: float,
        to_y: float,
        near: bool,
    ) -> list[tuple[float, float]]:
        """Map-space blends along army→destination, then project (deduped).

        Near targets prefer undershoot first so we do not park in the gulf west
        of Segesta when belief scale is slightly high.
        """
        blends = NEAR_PROJECTION_BLENDS if near else (1.0,)
        out: list[tuple[float, float]] = []
        seen: set[tuple[float, float]] = set()
        for blend in blends:
            mx = float(from_x) + float(blend) * (float(to_x) - float(from_x))
            my = float(from_y) + float(blend) * (float(to_y) - float(from_y))
            point = map_to_client(transform, (mx, my))
            if point is None:
                continue
            key = (round(point[0], 3), round(point[1], 3))
            if key in seen:
                continue
            seen.add(key)
            out.append(point)
        return out

    def _march_via_legacy_geometry(
        self,
        *,
        from_x: float,
        from_y: float,
        to_x: float,
        to_y: float,
        character_name: str,
        target_label: str,
        selection: StackSelection,
        baseline: int,
        dist: float,
    ) -> MarchOutcome:
        vision_outcome = None
        if self.locate_target is not None and target_label.strip():
            vision_outcome = self._try_vision_click(
                target_label=target_label,
                from_x=from_x,
                from_y=from_y,
                to_x=to_x,
                to_y=to_y,
                baseline=baseline,
                unit_cards=selection.unit_cards,
                character_name=character_name,
            )
            if vision_outcome is not None:
                return vision_outcome
        else:
            print("MARCH vision: off — legacy geometry probes", flush=True)

        click: tuple[float, float] | None = None
        cursor_changed = False
        tried: list[str] = []
        clamped_glyph: tuple[float, float] | None = None
        for step in self.step_candidates(dist):
            packed = self.destination_norm_ex(
                from_x=from_x,
                from_y=from_y,
                to_x=to_x,
                to_y=to_y,
                step_norm=step,
            )
            if packed is None:
                continue
            candidate, clamped = packed
            if not self._hover(candidate):
                tried.append(f"{step:.2f}:hover_failed")
                continue
            hovered = self.cursor_handle()
            if hovered == 0:
                tried.append(f"{step:.2f}:unreadable")
                continue
            changed = hovered != baseline
            tag = "glyph" if changed else "same"
            if clamped:
                tag += "+clamp"
            tried.append(f"{step:.2f}@({candidate[0]:.3f},{candidate[1]:.3f}) {tag}")
            if not changed:
                continue
            if clamped:
                if clamped_glyph is None:
                    clamped_glyph = candidate
                continue
            click = candidate
            cursor_changed = True
            break

        if click is None and clamped_glyph is not None:
            click = clamped_glyph
            cursor_changed = True

        if click is None:
            fallback_step = 0.18 if dist > NEAR_SETTLEMENT_MAP_DIST else 0.24
            click = self.destination_norm(
                from_x=from_x,
                from_y=from_y,
                to_x=to_x,
                to_y=to_y,
                step_norm=fallback_step,
            )
            if click is None:
                return self._refuse("no_move_cursor", selection.unit_cards)
            if not self._hover(click):
                return self._refuse("hover_failed", selection.unit_cards)
            print(
                f"MARCH probes: {'; '.join(tried) or 'none'} — "
                f"land fallback click=({click[0]:.3f},{click[1]:.3f})",
                flush=True,
            )
        else:
            print(
                f"MARCH probes: {'; '.join(tried)} — "
                f"glyph at ({click[0]:.3f},{click[1]:.3f})",
                flush=True,
            )

        return self._issue_click(
            click=click,
            from_x=from_x,
            from_y=from_y,
            to_x=to_x,
            to_y=to_y,
            unit_cards=selection.unit_cards,
            character_name=character_name or target_label,
            cursor_changed=cursor_changed,
            vision_used=False,
            calib_mode="legacy_geometry",
        )

    def besiege_via_vision(
        self,
        *,
        label: str = "",
        lists_row: tuple[float, float] | None = None,
        standing: str = "unknown",
        owner_raw: str = "",
        need_region_pan: bool = False,
        pan_dx: float = 0.0,
        pan_dy: float = 0.0,
        character_name: str = "",
        from_x: float | None = None,
        from_y: float | None = None,
    ) -> MarchOutcome:
        """View-first besiege: army already selected → scan ovals → sword → war Yes.

        Does **not** open Lists or use seed map XY for the click. ``lists_row`` /
        ``from_x`` / ``from_y`` / ``character_name`` / ``standing`` are ignored
        (call-site compat); standing comes from the view scan.
        """
        del lists_row, standing, character_name, from_x, from_y
        from comstar_game_ai.game_io.campaign.besiege_actuation import (
            DEFAULT_PAN_BINDINGS,
            BesiegeActuator,
        )

        if self.controller is None or self.hwnd is None:
            return self._refuse("no_controller")
        if self.scan_settlements is None and self.locate_target is None:
            return self._refuse("no_scan_settlements")

        selection = self._combat_director().selected_stack()
        if selection.unit_cards < 1:
            return self._refuse("stack_not_selected")

        cam = camera_config().get("bindings") or {}
        pan_bindings = dict(DEFAULT_PAN_BINDINGS)
        for key in ("pan_left", "pan_right", "pan_forward", "pan_back"):
            if cam.get(key):
                pan_bindings[key] = str(cam[key])

        actuator = BesiegeActuator(
            hwnd=self.hwnd,
            controller=self.controller,
            locate_target=self.locate_target,
            scan_settlements=self.scan_settlements,
            belief=self.belief,
            capture=self.capture,
            hover_dwell_s=self.hover_dwell_s,
            allow_region_pan=self.allow_region_pan,
            pan_bindings=pan_bindings,
            sleep=self.sleep,
            on_heartbeat=self.on_heartbeat,
        )
        if self.scan_settlements is not None:
            result = actuator.besiege_from_view(
                prefer_label=label,
                owner_raw=owner_raw,
                need_region_pan=need_region_pan,
                pan_dx=pan_dx,
                pan_dy=pan_dy,
            )
        else:
            result = actuator.besiege(
                label=label or "target",
                standing="unknown",
                owner_raw=owner_raw,
                need_region_pan=need_region_pan,
                pan_dx=pan_dx,
                pan_dy=pan_dy,
            )
        if not result.ordered:
            return self._refuse(result.reason or "besiege_failed")
        return MarchOutcome(
            ordered=True,
            reason=result.reason or "ok",
            unit_cards=selection.unit_cards,
            click_norm=result.click_norm,
            cursor_changed=result.cursor_changed,
            vision_used=result.vision_used,
            button="right",
            calib_mode="vision_besiege",
            projection_consistent=True,
            belief_refresh_ok=False,
        )

    def march(
        self,
        *,
        from_x: float,
        from_y: float,
        to_x: float,
        to_y: float,
        lists_row: tuple[float, float] | None = None,
        character_name: str = "",
        target_label: str = "",
        standing: str = "unknown",
        owner_raw: str = "",
    ) -> MarchOutcome:
        """Select the ordered stack and right-click the projected destination."""
        if self.use_vision_besiege and (
            self.scan_settlements is not None
            or (target_label and self.locate_target is not None)
        ):
            return self.besiege_via_vision(
                label=target_label,
                standing=standing,
                owner_raw=owner_raw,
                character_name=character_name,
            )
        if self.controller is None or self.hwnd is None:
            return self._refuse("no_controller")

        belief_from = (float(from_x), float(from_y))
        dist = self.map_distance(from_x=from_x, from_y=from_y, to_x=to_x, to_y=to_y)
        if dist < 1e-6:
            return self._refuse("already_at_target")

        live_from_xy: tuple[float, float] | None = None
        select_centre: tuple[float, float] | None = None
        verify_mode = ""
        belief_refresh_ok = False

        if self.use_map_projection:
            fit = self._current_fit()
            if fit is None or not fit.valid:
                return self._refuse("fit_invalid")
            # Scale may be derived from the frustum after pose reset; only refuse
            # here when projection is on and we will skip the pose path entirely.
            sequence = str(
                (camera_config().get("reset_sequence") or "locate_then_reset")
            ).lower()
            if sequence == "reset_then_locate":
                refused = self._ensure_canonical_pose(
                    from_xy=belief_from, already_located=False
                )
                if refused is not None:
                    return refused
            acquired = self.acquire_ordered_stack(
                from_x=from_x,
                from_y=from_y,
                preferred_row=lists_row,
                character_name=character_name,
            )
            if acquired is None:
                return self._refuse("stack_not_selected")
            selection, lists_row, verify_mode, select_centre = acquired
            belief_refresh_ok = verify_mode == "frustum"
            if sequence != "reset_then_locate":
                refused = self._ensure_canonical_pose(
                    from_xy=belief_from, already_located=True
                )
                if refused is not None:
                    return refused
            if self._require_anchor_scale() is None:
                return self._refuse("anchor_scale_unset")

            live_from_xy = self._measure_frustum_centre()
            if self.require_canonical_pose:
                if live_from_xy is None:
                    return self._refuse("frustum_missing_after_pose")

                if select_centre is not None:
                    drift = math.hypot(
                        live_from_xy[0] - select_centre[0],
                        live_from_xy[1] - select_centre[1],
                    )
                    if drift > POSE_FRUSTUM_DRIFT_MAP:
                        print(
                            f"MARCH refused: pose_frustum_drift "
                            f"select=({select_centre[0]:.1f},{select_centre[1]:.1f}) "
                            f"pose=({live_from_xy[0]:.1f},{live_from_xy[1]:.1f}) "
                            f"drift={drift:.1f}",
                            flush=True,
                        )
                        return self._refuse(
                            "pose_frustum_drift",
                            selection.unit_cards,
                            live_from_xy=live_from_xy,
                            belief_refresh_ok=belief_refresh_ok,
                        )

                belief_gap = math.hypot(
                    live_from_xy[0] - belief_from[0],
                    live_from_xy[1] - belief_from[1],
                )
                if belief_gap > ARMY_FRUSTUM_MATCH_MAP:
                    print(
                        f"MARCH refused: belief_from_mismatch "
                        f"belief=({belief_from[0]:.1f},{belief_from[1]:.1f}) "
                        f"live=({live_from_xy[0]:.1f},{live_from_xy[1]:.1f}) "
                        f"gap={belief_gap:.1f} — refresh belief from live frustum",
                        flush=True,
                    )
                    return self._refuse(
                        "belief_from_mismatch",
                        selection.unit_cards,
                        live_from_xy=live_from_xy,
                        belief_refresh_ok=belief_refresh_ok,
                    )

                from_x, from_y = live_from_xy
                dist = self.map_distance(
                    from_x=from_x, from_y=from_y, to_x=to_x, to_y=to_y
                )
                print(
                    f"MARCH live_from=({from_x:.1f},{from_y:.1f}) "
                    f"belief_from=({belief_from[0]:.1f},{belief_from[1]:.1f}) "
                    f"gap={belief_gap:.1f} dist_to_dest={dist:.1f}",
                    flush=True,
                )
            elif live_from_xy is not None:
                from_x, from_y = live_from_xy
                dist = self.map_distance(
                    from_x=from_x, from_y=from_y, to_x=to_x, to_y=to_y
                )
            else:
                live_from_xy = belief_from

            if verify_mode == "cards_unverified" and character_name:
                print(
                    f"MARCH select: unverified stack — will require glyph "
                    f"who={character_name}",
                    flush=True,
                )
        else:
            selection = self.acquire_any_stack(lists_row)
            if selection is None or selection.unit_cards < 1:
                return self._refuse("stack_not_selected")

        print(
            f"MARCH client={self._client_size_label()} (norms are client-relative) "
            f"from=({from_x:.1f},{from_y:.1f}) to=({to_x:.1f},{to_y:.1f}) "
            f"label={target_label or '-'} who={character_name or '-'} "
            f"cards={selection.unit_cards} dist={dist:.1f} "
            f"projection={self.use_map_projection}",
            flush=True,
        )

        self._hover(NEUTRAL_CURSOR_PROBE)
        baseline = self.cursor_handle()
        if baseline == 0:
            return self._refuse(
                "cursor_unreadable", selection.unit_cards, live_from_xy=live_from_xy,
                belief_refresh_ok=belief_refresh_ok,
            )

        if self.use_map_projection:
            self._note_fit("selection_change")
            if not self._keep_fit(fit):
                return self._refuse(
                    "fit_invalid",
                    selection.unit_cards,
                    live_from_xy=live_from_xy,
                    belief_refresh_ok=belief_refresh_ok,
                )
            outcome = self._march_closed_loop(
                from_x=from_x,
                from_y=from_y,
                to_x=to_x,
                to_y=to_y,
                lists_row=lists_row,
                character_name=character_name,
                target_label=target_label,
                selection=selection,
                baseline=baseline,
                live_from_xy=live_from_xy,
                belief_refresh_ok=belief_refresh_ok,
            )
            if outcome.ordered:
                return outcome
            if not self.allow_legacy_geometry:
                return outcome
            print(
                f"MARCH projection refused ({outcome.reason}) — "
                "legacy geometry fallback enabled",
                flush=True,
            )
            # Re-select after radar jump moved the camera.
            selection2 = self.acquire_any_stack(lists_row)
            if selection2 is None or selection2.unit_cards < 1:
                return outcome
            selection = selection2
            self._hover(NEUTRAL_CURSOR_PROBE)
            baseline = self.cursor_handle()
            if baseline == 0:
                return self._refuse(
                    "cursor_unreadable", selection.unit_cards, live_from_xy=live_from_xy,
                    belief_refresh_ok=belief_refresh_ok,
                )

        return self._march_via_legacy_geometry(
            from_x=from_x,
            from_y=from_y,
            to_x=to_x,
            to_y=to_y,
            character_name=character_name,
            target_label=target_label,
            selection=selection,
            baseline=baseline,
            dist=dist,
        )

    def _refuse(
        self,
        reason: str,
        unit_cards: int = 0,
        *,
        live_from_xy: tuple[float, float] | None = None,
        belief_refresh_ok: bool = False,
    ) -> MarchOutcome:
        self.last_reason = reason
        print(f"MARCH refused: {reason}", flush=True)
        _LOGGER.info("march refused: %s", reason)
        return MarchOutcome(
            ordered=False,
            reason=reason,
            unit_cards=unit_cards,
            live_from_xy=live_from_xy,
            belief_refresh_ok=belief_refresh_ok,
        )
