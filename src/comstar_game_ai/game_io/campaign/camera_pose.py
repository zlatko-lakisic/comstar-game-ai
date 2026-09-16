"""Campaign camera reset to the canonical pose before map→window projection.

Reset by saturation against a **clean** engine limit (zoom **in**), then a fixed
step out — never by reading current zoom/rotation and computing a delta. Verify
after quiesce; refuse with ``pose_unverified`` rather than projecting from an
unknown pose. Do not fold Map Overlay detection into AABB verify (Z3).

See ``docs/design/map-window-projection.md`` § Canonical camera pose and
``docs/canonical-zoom-surface-handoff.md``.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from comstar_game_ai.game_io.campaign.map_projection import detect_radar_frustum_map_aabb
from comstar_game_ai.shared.config import load_config

_LOGGER = logging.getLogger(__name__)

PoseCaptureFn = Callable[[], Any]
PoseSleepFn = Callable[[float], None]


@dataclass(frozen=True)
class FrustumMeasure:
    """Radar frustum AABB in map space."""

    map_min: tuple[float, float]
    map_max: tuple[float, float]

    @property
    def width(self) -> float:
        return float(self.map_max[0] - self.map_min[0])

    @property
    def height(self) -> float:
        return float(self.map_max[1] - self.map_min[1])

    @property
    def aspect(self) -> float:
        return self.width / max(self.height, 1e-6)

    @property
    def centre(self) -> tuple[float, float]:
        return (
            0.5 * (self.map_min[0] + self.map_max[0]),
            0.5 * (self.map_min[1] + self.map_max[1]),
        )


@dataclass(frozen=True)
class PoseCheckResult:
    ok: bool
    reason: str
    measured: FrustumMeasure | None = None
    expected_width: float | None = None
    failed_checks: tuple[str, ...] = ()


@dataclass
class CameraPoseDirector:
    """Drive the campaign camera to the configured canonical pose and verify it."""

    hwnd: int | None
    controller: Any
    capture: PoseCaptureFn
    sleep: PoseSleepFn = time.sleep
    config: dict[str, Any] | None = None
    army_match_map: float = 22.0
    last_pose_log: str = field(default="", init=False)

    def _cfg(self) -> dict[str, Any]:
        if self.config is not None:
            return self.config
        return (load_config().get("campaign") or {}).get("camera") or {}

    def _bindings(self) -> dict[str, str]:
        raw = self._cfg().get("bindings") or {}
        return {str(k): str(v) for k, v in raw.items()}

    def _chord(self, action: str) -> str | None:
        return self._bindings().get(action)

    def _tap(self, action: str, *, times: int = 1, dwell_ms: int = 40) -> bool:
        key = self._chord(action)
        if not key or self.controller is None:
            return False
        ok = True
        for _ in range(max(1, times)):
            if not self.controller.tap_key(key, dwell_ms=dwell_ms, hwnd=self.hwnd):
                ok = False
            self.sleep(0.05)
        return ok

    def measure_frustum(self) -> FrustumMeasure | None:
        image = self.capture()
        if image is None:
            return None
        aabb = detect_radar_frustum_map_aabb(image)
        if aabb is None:
            return None
        return FrustumMeasure(map_min=aabb[0], map_max=aabb[1])

    def quiesce(self) -> FrustumMeasure | None:
        """Wait until the frustum AABB is stable, or time out (None)."""
        cfg = self._cfg().get("quiesce") or {}
        stable_needed = int(cfg.get("stable_frames", 3))
        timeout_s = float(cfg.get("timeout_s", 4.0))
        epsilon = float(cfg.get("aabb_epsilon_map", 1.5))
        deadline = time.monotonic() + timeout_s
        previous: FrustumMeasure | None = None
        stable = 0
        while time.monotonic() < deadline:
            current = self.measure_frustum()
            if current is None:
                stable = 0
                previous = None
                self.sleep(0.15)
                continue
            if previous is not None and _aabb_close(previous, current, epsilon):
                stable += 1
                if stable >= stable_needed:
                    return current
            else:
                stable = 1
            previous = current
            self.sleep(0.15)
        _LOGGER.info("camera pose quiesce timed out")
        return None

    def reset_rotation(self) -> str:
        """North-up via ``point_to_north``, else bounded middle-drag unrotate.

        Returns the mechanism used: ``point_to_north`` | ``drag_unrotate`` | ``failed``.
        """
        if self._tap("point_to_north"):
            self.sleep(0.35)
            return "point_to_north"
        return self._drag_unrotate()

    def _drag_unrotate(self) -> str:
        """Bounded closed loop: middle-drag, keep improvements, reverse on regression."""
        if self.controller is None or self.hwnd is None:
            return "failed"
        if not hasattr(self.controller, "drag_client_norm"):
            _LOGGER.warning("drag_unrotate needs controller.drag_client_norm")
            return "failed"
        drag_cfg = self._cfg().get("drag_unrotate") or {}
        max_attempts = int(drag_cfg.get("max_attempts", 4))
        length = float(drag_cfg.get("drag_norm_length", 0.12))
        verify_cfg = self._cfg().get("verify") or {}
        aspect_min = float(verify_cfg.get("north_up_aspect_min", 0.55))

        baseline = self.quiesce()
        if baseline is None:
            return "failed"
        best_aspect = baseline.aspect
        direction = 1.0
        for attempt in range(max_attempts):
            start = (0.50 - 0.5 * direction * length, 0.42)
            end = (0.50 + 0.5 * direction * length, 0.42)
            # Middle button only — left drag selects / orders; right issues marches.
            if not self.controller.drag_client_norm(
                self.hwnd, start, end, button="middle"
            ):
                return "failed"
            self.sleep(0.25)
            after = self.quiesce()
            if after is None:
                return "failed"
            if after.aspect >= aspect_min and after.aspect >= best_aspect - 0.02:
                return "drag_unrotate"
            if after.aspect < best_aspect:
                direction *= -1.0
            else:
                best_aspect = after.aspect
            _LOGGER.info(
                "drag_unrotate attempt=%s aspect=%.3f best=%.3f dir=%s",
                attempt + 1,
                after.aspect,
                best_aspect,
                direction,
            )
        return "failed"

    def reset_zoom(self) -> bool:
        """Saturate zoom_in (hard clamp), then step out to the canonical zoom (Z1)."""
        cfg = self._cfg()
        pose = cfg.get("canonical_pose") or {}
        saturate = int(cfg.get("zoom_in_saturate_presses", 40))
        raw_steps = pose.get("zoom_steps_from_max_in", None)
        # Unset / null steps = stay at max-in (in-clamp verify / pre-sweep only).
        steps_out = 0 if raw_steps is None else int(raw_steps)
        # Extra presses guarantee the clamp even if we started mid-range.
        if not self._tap("zoom_in", times=saturate + 2, dwell_ms=35):
            return False
        self.sleep(0.2)
        if steps_out > 0 and not self._tap("zoom_out", times=steps_out, dwell_ms=35):
            return False
        self.sleep(0.25)
        return True

    def verify_in_clamp_surface(self) -> tuple[bool, dict[str, Any]]:
        """Z1: after max zoom-in, Z3 must still report the 3D map."""
        from comstar_game_ai.game_io.campaign.map_surface import check_map_surface

        image = self.capture()
        if image is None:
            return False, {"detail": "no_frame"}
        check = check_map_surface(image)
        ok = not check.is_map_overlay
        payload = check.as_log_dict()
        if not ok:
            _LOGGER.error("in-clamp surface is Map Overlay — neither extreme is safe: %s", payload)
        return ok, payload

    def verify(
        self,
        *,
        from_xy: tuple[float, float] | None = None,
        measured: FrustumMeasure | None = None,
    ) -> PoseCheckResult:
        """P5: AABB width (when fitted), north-up aspect, optional army-centre check."""
        cfg = self._cfg().get("verify") or {}
        expected = cfg.get("expected_aabb_width_map")
        tolerance = float(cfg.get("aabb_width_tolerance_map", 8.0))
        aspect_min = float(cfg.get("north_up_aspect_min", 0.55))

        frustum = measured if measured is not None else self.measure_frustum()
        if frustum is None:
            return PoseCheckResult(
                ok=False,
                reason="pose_unverified",
                failed_checks=("frustum_missing",),
            )

        failed: list[str] = []
        expected_w: float | None = None
        # Width expectation is optional until Z7 commits a value after a landed march.
        # Missing it must not block learning a safe pose.
        if expected is not None:
            expected_w = float(expected)
            if abs(frustum.width - expected_w) > tolerance:
                failed.append("aabb_width")

        if frustum.aspect < aspect_min:
            failed.append("north_up")

        if from_xy is not None:
            cx, cy = frustum.centre
            dist = math.hypot(cx - from_xy[0], cy - from_xy[1])
            if dist > self.army_match_map:
                failed.append("frustum_centre")

        if failed:
            return PoseCheckResult(
                ok=False,
                reason="pose_unverified",
                measured=frustum,
                expected_width=expected_w,
                failed_checks=tuple(failed),
            )
        return PoseCheckResult(
            ok=True,
            reason="pose_ok",
            measured=frustum,
            expected_width=expected_w,
        )

    def ensure_canonical(
        self,
        *,
        from_xy: tuple[float, float] | None = None,
        already_located: bool = True,
    ) -> PoseCheckResult:
        """Reset rotation then zoom, quiesce, verify.

        ``reset_sequence`` in config chooses locate-then-reset vs reset-then-locate
        at the march call site; this method only performs the reset+verify half.
        """
        _ = already_located  # sequencing is owned by the march director
        # Do not tap Escape here: on the campaign map Escape opens the main
        # menu / help sheet and steals the zoom keys that follow.
        rotation_mech = self.reset_rotation()
        if rotation_mech == "failed":
            return PoseCheckResult(
                ok=False,
                reason="pose_unverified",
                failed_checks=("rotation_reset",),
            )
        if not self.reset_zoom():
            return PoseCheckResult(
                ok=False,
                reason="pose_unverified",
                failed_checks=("zoom_reset",),
            )
        settled = self.quiesce()
        if settled is None:
            return PoseCheckResult(
                ok=False,
                reason="pose_unverified",
                failed_checks=("quiesce_timeout",),
            )
        result = self.verify(from_xy=from_xy, measured=settled)
        self.last_pose_log = (
            f"MARCH pose: ok={result.ok} rot={rotation_mech} "
            f"w={settled.width:.1f} h={settled.height:.1f} aspect={settled.aspect:.3f} "
            f"centre=({settled.centre[0]:.1f},{settled.centre[1]:.1f}) "
            f"expected_w={result.expected_width} failed={list(result.failed_checks)}"
        )
        print(self.last_pose_log, flush=True)
        _LOGGER.info("%s", self.last_pose_log)
        return result


def _aabb_close(a: FrustumMeasure, b: FrustumMeasure, epsilon: float) -> bool:
    return (
        abs(a.width - b.width) <= epsilon
        and abs(a.height - b.height) <= epsilon
        and abs(a.centre[0] - b.centre[0]) <= epsilon
        and abs(a.centre[1] - b.centre[1]) <= epsilon
    )


def camera_config() -> dict[str, Any]:
    return (load_config().get("campaign") or {}).get("camera") or {}
