"""Besiege from the current campaign view: scan ovals → sword → war-Yes.

No Lists. No seed map XY. Optional keyboard pan watches the radar frustum only
and never clicks the minimap (that clears army selection).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Literal

from comstar_game_ai.agent.belief.diplomacy import (
    DiplomaticStanding,
    mark_at_war,
    normalize_standing,
)
from comstar_game_ai.agent.belief.store import BeliefStore
from comstar_game_ai.game_io.campaign.camera_pose import FrustumMeasure
from comstar_game_ai.game_io.campaign.combat import read_cursor_handle
from comstar_game_ai.game_io.campaign.map_projection import detect_radar_frustum_map_aabb
from comstar_game_ai.game_io.campaign.map_target_vision import (
    MapTargetHit,
    SettlementViewHit,
    rank_attackable_settlements,
)
from comstar_game_ai.game_io.campaign.ui_mode import grab_rgb_image

if TYPE_CHECKING:
    from PIL import Image

    from comstar_game_ai.game_io.input.send_input import SendInputController

_LOGGER = logging.getLogger(__name__)

LocateTargetFn = Callable[["Image.Image", str], MapTargetHit | None]
ScanSettlementsFn = Callable[["Image.Image"], list[SettlementViewHit]]
ConfirmWarYesFn = Callable[["Image.Image"], tuple[float, float] | None]

PanKey = Literal["pan_left", "pan_right", "pan_forward", "pan_back"]

#: Operator pan chords. Prefer ``s`` for pan_back so it does not collide with
#: zoom_out ``x`` used by camera pose.
DEFAULT_PAN_BINDINGS: dict[str, str] = {
    "pan_left": "a",
    "pan_right": "d",
    "pan_forward": "w",
    "pan_back": "s",
}


@dataclass(frozen=True)
class BesiegeOutcome:
    ordered: bool
    reason: str
    click_norm: tuple[float, float] | None = None
    cursor_changed: bool = False
    vision_used: bool = False
    war_confirmed: bool = False
    camera_restarted: int = 0
    label: str = ""
    standing: str = ""


@dataclass
class BesiegeActuator:
    """Army-selected → view scan → sword hover → right-click → optional war Yes."""

    hwnd: int | None
    controller: SendInputController | None
    locate_target: LocateTargetFn | None = None
    scan_settlements: ScanSettlementsFn | None = None
    belief: BeliefStore | None = None
    capture: Callable[[], Image.Image | None] | None = None
    hover_dwell_s: float = 1.2
    allow_region_pan: bool = False
    pan_bindings: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_PAN_BINDINGS))
    pan_taps: int = 2
    max_camera_restarts: int = 2
    frustum_move_epsilon: float = 2.0
    confirm_war_yes: ConfirmWarYesFn | None = None
    sleep: Callable[[float], None] = time.sleep
    on_heartbeat: Callable[[], None] | None = None

    def _heartbeat(self) -> None:
        if self.on_heartbeat is None:
            return
        try:
            self.on_heartbeat()
        except Exception:  # noqa: BLE001
            _LOGGER.warning("besiege heartbeat failed", exc_info=True)

    def _grab(self) -> Image.Image | None:
        if self.capture is not None:
            return self.capture()
        if self.hwnd is None:
            return None
        return grab_rgb_image(self.hwnd)

    def _tap(self, key: str) -> bool:
        if self.controller is None or not key:
            return False
        return bool(self.controller.tap_key(key, dwell_ms=40, hwnd=self.hwnd))

    def measure_frustum(self, image: Image.Image | None = None) -> FrustumMeasure | None:
        frame = image if image is not None else self._grab()
        if frame is None:
            return None
        aabb = detect_radar_frustum_map_aabb(frame)
        if aabb is None:
            return None
        return FrustumMeasure(aabb[0], aabb[1])

    def camera_moved(
        self, before: FrustumMeasure | None, after: FrustumMeasure | None
    ) -> bool:
        if before is None or after is None:
            return False
        eps = self.frustum_move_epsilon
        return (
            abs(before.width - after.width) > eps
            or abs(before.height - after.height) > eps
            or abs(before.centre[0] - after.centre[0]) > eps
            or abs(before.centre[1] - after.centre[1]) > eps
        )

    def pan_region(
        self,
        *,
        dx_hint: float = 0.0,
        dy_hint: float = 0.0,
    ) -> None:
        """Keyboard-pan while watching the minimap frustum — never click the radar.

        ``dx_hint`` / ``dy_hint`` are map-space (east+, north+). Positive east → D,
        positive north → W.
        """
        if not self.allow_region_pan:
            return
        taps = max(1, int(self.pan_taps))
        keys: list[str] = []
        if abs(dx_hint) >= abs(dy_hint):
            if dx_hint > 0.5:
                keys.append(self.pan_bindings.get("pan_right", "d"))
            elif dx_hint < -0.5:
                keys.append(self.pan_bindings.get("pan_left", "a"))
        if abs(dy_hint) >= abs(dx_hint) * 0.5:
            if dy_hint > 0.5:
                keys.append(self.pan_bindings.get("pan_forward", "w"))
            elif dy_hint < -0.5:
                keys.append(self.pan_bindings.get("pan_back", "s"))
        if not keys:
            return
        before = self.measure_frustum()
        for _ in range(taps):
            for key in keys:
                self._heartbeat()
                self._tap(key)
                self.sleep(0.05)
        after = self.measure_frustum()
        if before is not None and after is not None:
            _LOGGER.info(
                "besiege pan: frustum (%.1f,%.1f)->(%.1f,%.1f) keys=%s",
                before.centre[0],
                before.centre[1],
                after.centre[0],
                after.centre[1],
                keys,
            )

    def _hover(self, point: tuple[float, float]) -> bool:
        if self.controller is None or self.hwnd is None:
            return False
        from comstar_game_ai.game_io.campaign.combat import client_norm_to_screen

        screen = client_norm_to_screen(self.hwnd, point[0], point[1])
        if screen is None:
            return False
        self.controller.move_mouse(*screen)
        self.sleep(0.15)
        self.controller.move_mouse(*screen)
        self.sleep(self.hover_dwell_s)
        return True

    def _right_click(self, point: tuple[float, float]) -> bool:
        if self.controller is None or self.hwnd is None:
            return False
        right = getattr(self.controller, "right_click_client_norm", None)
        if callable(right):
            return bool(right(self.hwnd, point[0], point[1], dwell_ms=60))
        if not self._hover(point):
            return False
        fn = getattr(self.controller, "right_click", None)
        if not callable(fn):
            return False
        from comstar_game_ai.game_io.campaign.combat import client_norm_to_screen

        screen = client_norm_to_screen(self.hwnd, point[0], point[1])
        if screen is None:
            return False
        return bool(fn(*screen))

    def _click_norm(self, point: tuple[float, float]) -> bool:
        if self.controller is None or self.hwnd is None:
            return False
        return bool(
            self.controller.click_client_norm(self.hwnd, point[0], point[1], dwell_ms=60)
        )

    def default_confirm_war_yes(self, image: Image.Image) -> tuple[float, float] | None:
        """Locate the green Yes/accept on a declare-war confirm dialog."""
        from comstar_game_ai.game_io.campaign.modal import (
            localize_colored_modal_buttons,
            localize_left_panel_decision_buttons,
        )

        for locate in (localize_colored_modal_buttons, localize_left_panel_decision_buttons):
            buttons = locate(image) or ()
            for btn in buttons:
                if getattr(btn, "action", "") == "accept":
                    return (float(btn.x_norm), float(btn.y_norm))
        return None

    def confirm_declare_war(self, *, owner_raw: str = "") -> bool:
        self.sleep(0.4)
        self._heartbeat()
        frame = self._grab()
        if frame is None:
            return False
        locate = self.confirm_war_yes or self.default_confirm_war_yes
        point = locate(frame)
        if point is None:
            _LOGGER.warning("besiege: war confirm Yes not found")
            return False
        if not self._click_norm(point):
            return False
        if self.belief is not None and owner_raw:
            mark_at_war(self.belief, owner_raw)
        return True

    def _try_sword_click(
        self,
        *,
        click: tuple[float, float],
        standing: str,
        owner_raw: str,
        label: str,
        restarts: int,
    ) -> BesiegeOutcome | None:
        """Hover; if sword glyph, right-click (+ war Yes). None = try next candidate."""
        baseline_cursor = read_cursor_handle()
        if not self._hover(click):
            return BesiegeOutcome(
                False,
                "hover_failed",
                click_norm=click,
                vision_used=True,
                camera_restarted=restarts,
                label=label,
                standing=standing,
            )
        hovered = read_cursor_handle()
        if hovered == 0 or hovered == baseline_cursor:
            _LOGGER.info("besiege: no sword on %s @ (%.3f,%.3f)", label, click[0], click[1])
            return None

        if not self._right_click(click):
            return BesiegeOutcome(
                False,
                "right_click_failed",
                click_norm=click,
                vision_used=True,
                cursor_changed=True,
                camera_restarted=restarts,
                label=label,
                standing=standing,
            )

        standing_n = normalize_standing(standing)
        war_confirmed = False
        if standing_n in {"neutral", "ally"}:
            war_confirmed = self.confirm_declare_war(owner_raw=owner_raw)
            if not war_confirmed:
                return BesiegeOutcome(
                    False,
                    "war_confirm_failed",
                    click_norm=click,
                    vision_used=True,
                    cursor_changed=True,
                    camera_restarted=restarts,
                    label=label,
                    standing=standing,
                )

        return BesiegeOutcome(
            True,
            "ok",
            click_norm=click,
            vision_used=True,
            cursor_changed=True,
            war_confirmed=war_confirmed,
            camera_restarted=restarts,
            label=label,
            standing=standing,
        )

    def besiege_from_view(
        self,
        *,
        prefer_label: str = "",
        owner_raw: str = "",
        need_region_pan: bool = False,
        pan_dx: float = 0.0,
        pan_dy: float = 0.0,
    ) -> BesiegeOutcome:
        """Scan the current frame for attackable ovals; sword-gate each in rank order."""
        if self.scan_settlements is None:
            return BesiegeOutcome(False, "no_scan_settlements")
        if self.controller is None or self.hwnd is None:
            return BesiegeOutcome(False, "no_controller")

        restarts = 0
        while restarts <= self.max_camera_restarts:
            self._heartbeat()
            if need_region_pan and self.allow_region_pan:
                self.pan_region(dx_hint=pan_dx, dy_hint=pan_dy)

            baseline = self.measure_frustum()
            frame = self._grab()
            if frame is None:
                return BesiegeOutcome(False, "no_frame", camera_restarted=restarts)

            pre_vision = self.measure_frustum(frame)
            hits = self.scan_settlements(frame) or []
            post_vision = self.measure_frustum()
            if self.camera_moved(pre_vision or baseline, post_vision):
                restarts += 1
                _LOGGER.warning(
                    "besiege: camera moved during scan — restart %s", restarts
                )
                continue

            ranked = rank_attackable_settlements(hits, prefer_label=prefer_label)
            if not ranked:
                return BesiegeOutcome(
                    False,
                    "no_attackable_in_view",
                    vision_used=True,
                    camera_restarted=restarts,
                )

            # Click points must come from the CV detector (or a test inject),
            # never from a model coordinate field (settlement-detector S2/S4).
            clickable = [h for h in ranked if h.click_norm is not None]
            if not clickable:
                return BesiegeOutcome(
                    False,
                    "no_detector_click_point",
                    vision_used=True,
                    camera_restarted=restarts,
                )

            print(
                "MARCH besiege view: "
                + ", ".join(f"{h.label}[{h.standing}]" for h in clickable[:6]),
                flush=True,
            )

            last_no_sword: BesiegeOutcome | None = None
            for hit in clickable:
                self._heartbeat()
                click = hit.click_norm
                assert click is not None
                outcome = self._try_sword_click(
                    click=click,
                    standing=hit.standing,
                    owner_raw=owner_raw,
                    label=hit.label,
                    restarts=restarts,
                )
                if outcome is None:
                    last_no_sword = BesiegeOutcome(
                        False,
                        "no_sword_glyph",
                        click_norm=click,
                        vision_used=True,
                        cursor_changed=False,
                        camera_restarted=restarts,
                        label=hit.label,
                        standing=hit.standing,
                    )
                    continue
                return outcome

            return last_no_sword or BesiegeOutcome(
                False,
                "no_sword_glyph",
                vision_used=True,
                camera_restarted=restarts,
            )

        return BesiegeOutcome(False, "camera_unstable", camera_restarted=restarts)

    def besiege(
        self,
        *,
        label: str,
        standing: DiplomaticStanding | str = "unknown",
        owner_raw: str = "",
        need_region_pan: bool = False,
        pan_dx: float = 0.0,
        pan_dy: float = 0.0,
    ) -> BesiegeOutcome:
        """View-first when scan is wired; else single-label locate (tests/legacy)."""
        if self.scan_settlements is not None:
            return self.besiege_from_view(
                prefer_label=label,
                owner_raw=owner_raw,
                need_region_pan=need_region_pan,
                pan_dx=pan_dx,
                pan_dy=pan_dy,
            )
        if self.locate_target is None:
            return BesiegeOutcome(False, "no_locate_target")
        if self.controller is None or self.hwnd is None:
            return BesiegeOutcome(False, "no_controller")

        standing_n = normalize_standing(str(standing))
        restarts = 0

        while restarts <= self.max_camera_restarts:
            self._heartbeat()
            if need_region_pan and self.allow_region_pan:
                self.pan_region(dx_hint=pan_dx, dy_hint=pan_dy)

            baseline = self.measure_frustum()
            frame = self._grab()
            if frame is None:
                return BesiegeOutcome(False, "no_frame", camera_restarted=restarts)

            pre_vision = self.measure_frustum(frame)
            hit = self.locate_target(frame, label)
            post_vision = self.measure_frustum()
            if self.camera_moved(pre_vision or baseline, post_vision):
                restarts += 1
                _LOGGER.warning(
                    "besiege: camera moved during vision — restart %s", restarts
                )
                continue

            if hit is None or not hit.found or hit.click_norm is None:
                return BesiegeOutcome(
                    False,
                    "vision_miss",
                    vision_used=True,
                    camera_restarted=restarts,
                )

            hit_standing = getattr(hit, "standing", None) or "unknown"
            if hit_standing == "unknown":
                hit_standing = standing_n
            outcome = self._try_sword_click(
                click=hit.click_norm,
                standing=str(hit_standing),
                owner_raw=owner_raw,
                label=label,
                restarts=restarts,
            )
            if outcome is None:
                return BesiegeOutcome(
                    False,
                    "no_sword_glyph",
                    click_norm=hit.click_norm,
                    vision_used=True,
                    cursor_changed=False,
                    camera_restarted=restarts,
                    label=label,
                    standing=str(hit_standing),
                )
            return outcome

        return BesiegeOutcome(False, "camera_unstable", camera_restarted=restarts)


def never_click_minimap(*_args, **_kwargs) -> None:
    """Hard guard: radar/minimap clicks deselect the army. Do not call."""
    raise RuntimeError(
        "minimap click forbidden while army selected — use keyboard pan and watch frustum only"
    )
