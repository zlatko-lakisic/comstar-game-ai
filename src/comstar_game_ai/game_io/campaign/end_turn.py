"""End Turn actuation for Rome campaign map."""

from __future__ import annotations

import logging
import time

import win32gui

from comstar_game_ai.game_io.campaign.ui_mode import grab_rgb_image
from comstar_game_ai.game_io.input.directinput import click_screen, directinput_available, hotkey_shift_enter, tap_key
from comstar_game_ai.game_io.input.game_focus import game_input_session, post_vk_key, with_game_input
from comstar_game_ai.game_io.input.send_input import SendInputController
from comstar_game_ai.game_io.logs.turn_boundary import latest_turn_end, wait_for_turn_end
from comstar_game_ai.game_io.window import get_foreground_hwnd
from comstar_game_ai.shared.config import load_config

_LOGGER = logging.getLogger(__name__)

CONSOLE_TOGGLE_KEY = "`"

# Measured centre of the red horn button on the lower-right HUD (1920x1080 client).
# Only used when the button cannot be located visually.
END_TURN_CLICK_CANDIDATES: list[tuple[float, float]] = [
    (0.980, 0.973),
]


def localize_end_turn_button(image) -> tuple[float, float] | None:
    """Centre (normalised) of the red horn End Turn button on the lower-right HUD.

    The button is the only saturated red disc in that corner, so its position can be
    measured per frame instead of guessed — fixed norms miss it on other layouts, and a
    miss lands on the map, which selects units or opens settlement panels.
    """
    import numpy as np

    rgb = np.asarray(image.convert("RGB")).astype(np.int16)
    height, width = rgb.shape[:2]
    r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
    red = (r >= 110) & (r <= 210) & (g <= 80) & (b <= 80) & (r >= g + 60) & (r >= b + 60)

    y0, x0 = int(height * 0.88), int(width * 0.88)
    corner = red[y0:, x0:]
    if corner.sum() < 250:
        return None
    ys, xs = np.where(corner)
    cx = x0 + (float(xs.min()) + float(xs.max())) / 2.0
    cy = y0 + (float(ys.min()) + float(ys.max())) / 2.0
    # A disc, not a smear of red roofs: sides within 60% of each other.
    span_x = float(xs.max() - xs.min()) + 1.0
    span_y = float(ys.max() - ys.min()) + 1.0
    if min(span_x, span_y) < max(span_x, span_y) * 0.6:
        return None
    return cx / width, cy / height


def _client_to_screen(hwnd: int, x_norm: float, y_norm: float) -> tuple[int, int] | None:
    try:
        left, top, right, bottom = win32gui.GetClientRect(hwnd)
        w = max(right - left, 1)
        h = max(bottom - top, 1)
        cx = int(w * max(0.0, min(1.0, x_norm)))
        cy = int(h * max(0.0, min(1.0, y_norm)))
        return win32gui.ClientToScreen(hwnd, (cx, cy))
    except Exception:
        return None


def _focus_game(hwnd: int, input_controller: SendInputController, *, attempts: int = 10) -> bool:
    for _ in range(attempts):
        with game_input_session(hwnd):
            if get_foreground_hwnd() == hwnd:
                return True
        time.sleep(0.12)
    return False


def _try_after_actuation(
    baseline: int | None,
    method: str,
    *,
    timeout_s: float = 8.0,
) -> tuple[bool, str]:
    """Did this actuation end the turn? Only a later autosaved turn number says yes.

    The timeout has to outlast Rome writing the save itself, or a method that worked is
    scored as a miss and the next one clicks again mid-save.
    """
    turn = wait_for_turn_end(baseline, timeout_s=timeout_s)
    if turn is None:
        return False, ""
    _LOGGER.info("turn ended via %s (autosaved turn %s)", method, turn)
    return True, method


def end_turn_campaign(
    *,
    hwnd: int,
    input_controller: SendInputController,
    console_open: bool,
    dwell_ms: int = 40,
) -> tuple[bool, str]:
    """
    Try to end the player turn. Returns (success, method_used).

    Rome uses DirectInput — pydirectinput scan codes + HUD click beat SendInput alone.
    """
    baseline = latest_turn_end()

    if not _focus_game(hwnd, input_controller):
        return False, "focus_failed"

    if console_open:
        input_controller.tap_key(CONSOLE_TOGGLE_KEY, dwell_ms=dwell_ms, hwnd=hwnd)
        time.sleep(0.25)
        _focus_game(hwnd, input_controller, attempts=5)

    # 1) pydirectinput Shift+Enter (DirectInput path)
    if directinput_available():
        with_game_input(hwnd, hotkey_shift_enter)
        ok, tag = _try_after_actuation(baseline, "pydirect_shift_enter", timeout_s=10.0)
        if ok:
            return True, tag
        _focus_game(hwnd, input_controller, attempts=3)

    # 2) SendInput scan codes (thread attached during chord)
    input_controller.chord_scancode("shift", "enter", dwell_ms=max(dwell_ms, 80), hwnd=hwnd)
    ok, tag = _try_after_actuation(baseline, "scancode_shift_enter", timeout_s=8.0)
    if ok:
        return True, tag

    # 3) Click the End Turn button, located visually so a miss cannot hit the map.
    cfg = load_config()
    custom = cfg.get("campaign", {}).get("end_turn_click_norm")
    candidates: list[tuple[float, float]] = []
    frame = grab_rgb_image(hwnd)
    located = localize_end_turn_button(frame) if frame is not None else None
    if located is not None:
        _LOGGER.info("End turn button located at norm=(%.3f, %.3f)", *located)
        candidates.append(located)
    if isinstance(custom, (list, tuple)) and len(custom) == 2:
        candidates.append((float(custom[0]), float(custom[1])))
    candidates.extend(END_TURN_CLICK_CANDIDATES)

    seen: set[tuple[float, float]] = set()
    for x_norm, y_norm in candidates:
        key = (round(x_norm, 3), round(y_norm, 3))
        if key in seen:
            continue
        seen.add(key)
        pt = _client_to_screen(hwnd, x_norm, y_norm)
        if pt is None:
            continue
        sx, sy = pt
        _LOGGER.info("End turn click attempt norm=(%.2f, %.2f) screen=(%s, %s)", x_norm, y_norm, sx, sy)

        def _click() -> bool:
            if directinput_available():
                return click_screen(sx, sy)
            return input_controller.click(sx, sy, dwell_ms=max(dwell_ms, 50))

        with_game_input(hwnd, _click, activate_click=False)
        ok, tag = _try_after_actuation(baseline, f"click_{x_norm}_{y_norm}", timeout_s=8.0)
        if ok:
            return True, tag

    return False, "no_turn_boundary"
