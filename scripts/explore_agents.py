"""Select the starting spy and diplomat and walk their selection HUD.

Does not disband and does not end the turn. Send / path-commit phases
are live orders — only run them when that mutation is intended.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import ctypes
import win32gui

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from comstar_game_ai.game_io.campaign import modal, ui_atlas, ui_mode
from comstar_game_ai.game_io.input.send_input import (
    INPUT,
    INPUT_MOUSE,
    MOUSEEVENTF_LEFTDOWN,
    MOUSEEVENTF_LEFTUP,
    MOUSEINPUT,
    SendInputController,
)

MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
from comstar_game_ai.game_io.window import find_game_window
from comstar_game_ai.shared.config import load_config

OUT = ROOT / "data/runtime/sweep"

# Lists sub-tabs under the overview title, left to right.
LISTS_SUBTABS = {
    "settlements": (0.36, 0.259),
    "military": (0.50, 0.259),
    "agents": (0.65, 0.259),
}
# First data row and the locate magnifier (footer button 1). Never click button 3.
LISTS_FIRST_ROW = (0.40, 0.36)
LISTS_SECOND_ROW = (0.40, 0.405)
# Magnifier on the agent detail pane (right of the hooded Agent Hub disc).
LISTS_LOCATE = (0.72, 0.52)
LISTS_HUB = (0.68, 0.52)


def shot(hwnd, name: str):
    image = ui_mode.grab_rgb_image(hwnd)
    image.save(OUT / f"{name}.png")
    print(
        f"{name}: panel={modal.panel_bounds(image)} "
        f"mode={ui_mode.classify_campaign_image(image).mode.value}"
    )
    return image


def hover(pad, hwnd, nx: float, ny: float, name: str, dwell: float = 1.35):
    left, top, right, bottom = win32gui.GetClientRect(hwnd)
    sx, sy = win32gui.ClientToScreen(
        hwnd, (int(round(nx * (right - left))), int(round(ny * (bottom - top))))
    )
    pad.move_mouse(sx, sy)
    time.sleep(0.12)
    pad.move_mouse(sx, sy)
    time.sleep(dwell)
    return shot(hwnd, name)


def click(pad, hwnd, nx: float, ny: float, wait: float = 1.15):
    pad.click_client_norm(hwnd, nx, ny)
    time.sleep(wait)


def _client_to_screen(hwnd, nx: float, ny: float) -> tuple[int, int]:
    left, top, right, bottom = win32gui.GetClientRect(hwnd)
    return win32gui.ClientToScreen(
        hwnd, (int(round(nx * (right - left))), int(round(ny * (bottom - top))))
    )


def _button(pad, down: bool) -> bool:
    flag = MOUSEEVENTF_LEFTDOWN if down else MOUSEEVENTF_LEFTUP
    inp = INPUT()
    inp.type = INPUT_MOUSE
    inp.union.mi = MOUSEINPUT(0, 0, 0, flag, 0, 0)
    return pad._user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT)) == 1


def setup():
    cfg = load_config()
    hwnd = find_game_window(cfg.get("game", {}).get("window_title_substrings", ["Rome"])).hwnd
    pad = SendInputController()
    pad.focus_window(hwnd)
    time.sleep(0.35)
    return hwnd, pad


def main() -> int:
    phase = sys.argv[1] if len(sys.argv) > 1 else "snapshot"
    hwnd, pad = setup()

    if phase == "snapshot":
        shot(hwnd, "agent_snap")
        return 0

    if phase == "home":
        pad.tap_key("home", hwnd=hwnd)
        time.sleep(1.4)
        shot(hwnd, "agent_home")
        return 0

    if phase == "lists":
        pad.chord_scancode("ctrl", "5", hwnd=hwnd)
        time.sleep(1.4)
        shot(hwnd, "agent_lists")
        return 0

    if phase == "lists_agents":
        click(pad, hwnd, *LISTS_SUBTABS["agents"], wait=1.2)
        im = shot(hwnd, "agent_lists_agents")
        im.crop((480, 120, 1450, 980)).save(OUT / "crop_agent_lists_agents.png")
        return 0

    if phase == "lists_row":
        index = int(sys.argv[2]) if len(sys.argv) > 2 else 0
        y = LISTS_FIRST_ROW[1] + index * 0.045
        click(pad, hwnd, LISTS_FIRST_ROW[0], y, wait=0.9)
        im = shot(hwnd, f"agent_lists_detail_{index}")
        im.crop((480, 120, 1450, 980)).save(OUT / f"crop_agent_lists_detail_{index}.png")
        return 0

    if phase == "locate_row":
        index = int(sys.argv[2]) if len(sys.argv) > 2 else 0
        # Rows step down the list; first data row ~0.32, ~0.045 each.
        y = LISTS_FIRST_ROW[1] + index * 0.045
        click(pad, hwnd, LISTS_FIRST_ROW[0], y, wait=0.8)
        shot(hwnd, f"agent_lists_row_{index}")
        click(pad, hwnd, *LISTS_LOCATE, wait=1.6)
        im = shot(hwnd, f"agent_located_{index}")
        im.crop((0, 700, 1920, 1080)).save(OUT / f"crop_agent_hud_{index}.png")
        return 0

    if phase == "click_map":
        # Re-click the likely agent under the camera centre after locate.
        nx = float(sys.argv[2]) if len(sys.argv) > 2 else 0.50
        ny = float(sys.argv[3]) if len(sys.argv) > 3 else 0.48
        click(pad, hwnd, nx, ny, wait=1.2)
        im = shot(hwnd, "agent_selected")
        im.crop((0, 700, 1920, 1080)).save(OUT / "crop_agent_selected_hud.png")
        return 0

    if phase == "hover_hud":
        prefix = sys.argv[2] if len(sys.argv) > 2 else "hud"
        # Centres measured off grid overlays on agent_located_0.png (1920x1080).
        for name, x, y in (
            ("left_1", 0.090, 0.960),
            ("left_2", 0.120, 0.960),
            ("left_3", 0.148, 0.960),
            ("portrait", 0.040, 0.855),
            ("retinue_slot", 0.300, 0.880),
            ("disband", 0.715, 0.940),
            ("mid_locate", 0.655, 0.940),
            ("hub_tab", 0.524, 0.967),
            ("send_row1", 0.900, 0.785),
            ("send_row2", 0.900, 0.815),
            ("send_hub", 0.855, 0.935),
        ):
            im = hover(pad, hwnd, x, y, f"{prefix}_{name}")
            im.crop((0, 640, 1920, 1080)).save(OUT / f"crop_{prefix}_{name}.png")
        return 0

    if phase == "click_left_info":
        click(pad, hwnd, 0.090, 0.960, wait=1.4)
        im = shot(hwnd, "agent_left_info")
        im.crop((0, 400, 800, 1080)).save(OUT / "crop_agent_left_info.png")
        return 0

    if phase == "open_hub":
        nx = float(sys.argv[2]) if len(sys.argv) > 2 else 0.855
        ny = float(sys.argv[3]) if len(sys.argv) > 3 else 0.935
        click(pad, hwnd, nx, ny, wait=1.5)
        im = shot(hwnd, "agent_hub_from_hud")
        im.crop((480, 120, 1450, 980)).save(OUT / "crop_agent_hub_from_hud.png")
        return 0

    if phase == "overview_hub":
        pad.chord_scancode("ctrl", "7", hwnd=hwnd)
        time.sleep(1.5)
        im = shot(hwnd, "agent_hub_ctrl7")
        im.crop((480, 120, 1450, 980)).save(OUT / "crop_agent_hub_ctrl7.png")
        return 0

    if phase == "hub_hover":
        for name, x, y in (
            ("filter_1", 0.34, 0.24),
            ("confirm", 0.50, 0.90),
            ("target_1", 0.50, 0.55),
            ("close", *ui_atlas.OVERVIEW_FRAME.close_x),
        ):
            hover(pad, hwnd, x, y, f"hub_{name}")
        return 0

    if phase == "close_x":
        if len(sys.argv) >= 4:
            x, y = float(sys.argv[2]), float(sys.argv[3])
        else:
            x, y = ui_atlas.OVERVIEW_FRAME.close_x
        click(pad, hwnd, x, y, wait=1.3)
        shot(hwnd, "agent_after_close")
        return 0

    if phase == "rclick_xy":
        nx = float(sys.argv[2])
        ny = float(sys.argv[3])
        name = sys.argv[4] if len(sys.argv) > 4 else "agent_rclick"
        wait = float(sys.argv[5]) if len(sys.argv) > 5 else 2.0
        sx, sy = _client_to_screen(hwnd, nx, ny)
        pad.move_mouse(sx, sy)
        time.sleep(0.35)
        hover(pad, hwnd, nx, ny, f"{name}_hover", dwell=1.0)
        inp_down = INPUT()
        inp_down.type = INPUT_MOUSE
        inp_down.union.mi = MOUSEINPUT(0, 0, 0, MOUSEEVENTF_RIGHTDOWN, 0, 0)
        inp_up = INPUT()
        inp_up.type = INPUT_MOUSE
        inp_up.union.mi = MOUSEINPUT(0, 0, 0, MOUSEEVENTF_RIGHTUP, 0, 0)
        pad._user32.SendInput(1, ctypes.byref(inp_down), ctypes.sizeof(INPUT))
        time.sleep(0.05)
        pad._user32.SendInput(1, ctypes.byref(inp_up), ctypes.sizeof(INPUT))
        time.sleep(wait)
        im = shot(hwnd, name)
        im.crop((0, 200, 1920, 1080)).save(OUT / f"crop_{name}.png")
        return 0

    if phase == "click_xy":
        nx = float(sys.argv[2])
        ny = float(sys.argv[3])
        name = sys.argv[4] if len(sys.argv) > 4 else "agent_click"
        wait = float(sys.argv[5]) if len(sys.argv) > 5 else 1.6
        click(pad, hwnd, nx, ny, wait=wait)
        im = shot(hwnd, name)
        im.crop((0, 640, 1920, 1080)).save(OUT / f"crop_{name}.png")
        return 0

    if phase == "path_commit":
        # Hold from the agent and release on a destination so the move issues.
        sx, sy = _client_to_screen(hwnd, 0.50, 0.48)
        dx = float(sys.argv[2]) if len(sys.argv) > 2 else 0.58
        dy = float(sys.argv[3]) if len(sys.argv) > 3 else 0.38
        ex, ey = _client_to_screen(hwnd, dx, dy)
        pad.move_mouse(sx, sy)
        time.sleep(0.15)
        _button(pad, True)
        time.sleep(0.12)
        pad.move_mouse(ex, ey)
        time.sleep(0.8)
        shot(hwnd, "agent_path_held")
        _button(pad, False)
        time.sleep(1.8)
        im = shot(hwnd, "agent_path_committed")
        im.crop((0, 640, 1920, 1080)).save(OUT / "crop_agent_path_committed.png")
        return 0

    if phase == "hub_confirm":
        nx = float(sys.argv[2]) if len(sys.argv) > 2 else 0.62
        ny = float(sys.argv[3]) if len(sys.argv) > 3 else 0.88
        click(pad, hwnd, nx, ny, wait=1.8)
        im = shot(hwnd, "agent_hub_confirmed")
        im.crop((480, 120, 1450, 980)).save(OUT / "crop_agent_hub_confirmed.png")
        return 0

    if phase == "path_preview":
        # Hold from the selected agent (screen centre-ish) out, capture, return.
        sx, sy = _client_to_screen(hwnd, 0.50, 0.48)
        dx, dy = _client_to_screen(hwnd, 0.58, 0.42)
        pad.move_mouse(sx, sy)
        time.sleep(0.15)
        _button(pad, True)
        time.sleep(0.12)
        pad.move_mouse(dx, dy)
        time.sleep(0.8)
        shot(hwnd, "agent_path_preview")
        pad.move_mouse(sx, sy)
        time.sleep(0.2)
        _button(pad, False)
        time.sleep(0.6)
        shot(hwnd, "agent_path_released")
        return 0

    raise SystemExit(f"unknown phase {phase}")


if __name__ == "__main__":
    raise SystemExit(main())
