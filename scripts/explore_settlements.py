"""Walk owned-settlement construction, recruitment, and the building browser.

Hover only on build/recruit icons — a click queues and spends money.
Close with the panel X, not Escape. Do not end the turn or set the capital.
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
    MOUSEINPUT,
    SendInputController,
)
from comstar_game_ai.game_io.window import find_game_window
from comstar_game_ai.shared.config import load_config

OUT = ROOT / "data/runtime/sweep"

MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010

# Right-edge construction / recruitment dock (measured atlas).
CONSTRUCT_CLOSE = ui_atlas.BY_ID["construction_window"].geometry.close_x
BROWSER_CLOSE = ui_atlas.BY_ID["building_browser"].geometry.close_x
OVERVIEW_CLOSE = ui_atlas.OVERVIEW_FRAME.close_x

# Construction icon grid on the right dock, walked left-to-right / top-to-bottom.
CONSTRUCT_ICONS = (
    (0.90, 0.52),
    (0.935, 0.52),
    (0.97, 0.52),
    (0.90, 0.58),
    (0.935, 0.58),
    (0.97, 0.58),
    (0.90, 0.64),
    (0.935, 0.64),
    (0.97, 0.64),
    (0.90, 0.72),
    (0.935, 0.72),
    (0.97, 0.72),
)


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


def rclick(pad, hwnd, nx: float, ny: float, wait: float = 1.4):
    left, top, right, bottom = win32gui.GetClientRect(hwnd)
    sx, sy = win32gui.ClientToScreen(
        hwnd, (int(round(nx * (right - left))), int(round(ny * (bottom - top))))
    )
    pad.move_mouse(sx, sy)
    time.sleep(0.2)
    down = INPUT()
    down.type = INPUT_MOUSE
    down.union.mi = MOUSEINPUT(0, 0, 0, MOUSEEVENTF_RIGHTDOWN, 0, 0)
    up = INPUT()
    up.type = INPUT_MOUSE
    up.union.mi = MOUSEINPUT(0, 0, 0, MOUSEEVENTF_RIGHTUP, 0, 0)
    pad._user32.SendInput(1, ctypes.byref(down), ctypes.sizeof(INPUT))
    time.sleep(0.05)
    pad._user32.SendInput(1, ctypes.byref(up), ctypes.sizeof(INPUT))
    time.sleep(wait)


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
        shot(hwnd, "town_snap")
        return 0

    if phase == "home":
        pad.tap_key("home", hwnd=hwnd)
        time.sleep(1.5)
        im = shot(hwnd, "town_home")
        im.crop((0, 640, 1920, 1080)).save(OUT / "crop_town_home.png")
        return 0

    if phase == "construct":
        pad.tap_key("6", hwnd=hwnd)
        time.sleep(1.3)
        im = shot(hwnd, "town_construct")
        im.crop((1400, 400, 1920, 1080)).save(OUT / "crop_town_construct.png")
        return 0

    if phase == "recruit":
        pad.tap_key("5", hwnd=hwnd)
        time.sleep(1.3)
        im = shot(hwnd, "town_recruit")
        im.crop((1400, 400, 1920, 1080)).save(OUT / "crop_town_recruit.png")
        return 0

    if phase == "hover_construct":
        prefix = sys.argv[2] if len(sys.argv) > 2 else "c"
        for i, (x, y) in enumerate(CONSTRUCT_ICONS, start=1):
            im = hover(pad, hwnd, x, y, f"{prefix}_icon_{i:02d}")
            im.crop((1200, 350, 1920, 1080)).save(OUT / f"crop_{prefix}_icon_{i:02d}.png")
        return 0

    if phase == "hover_many":
        # pairs: name x y [dwell]
        args = sys.argv[2:]
        i = 0
        while i + 2 < len(args):
            name, nx, ny = args[i], float(args[i + 1]), float(args[i + 2])
            i += 3
            im = hover(pad, hwnd, nx, ny, name)
            im.crop((400, 200, 1920, 1080)).save(OUT / f"crop_{name}.png")
        return 0

    if phase == "hover_xy":
        nx, ny = float(sys.argv[2]), float(sys.argv[3])
        name = sys.argv[4] if len(sys.argv) > 4 else "town_hover"
        im = hover(pad, hwnd, nx, ny, name, dwell=float(sys.argv[5]) if len(sys.argv) > 5 else 1.45)
        im.crop((400, 200, 1920, 1080)).save(OUT / f"crop_{name}.png")
        return 0

    if phase == "hud_tab":
        # buildings / army / agents / fleets HUD tabs
        name = sys.argv[2] if len(sys.argv) > 2 else "buildings"
        centres = {
            "buildings": (0.436, 0.967),
            "army": (0.480, 0.967),
            "agents": (0.524, 0.967),
            "fleets": (0.568, 0.967),
        }
        click(pad, hwnd, *centres[name], wait=1.2)
        im = shot(hwnd, f"town_hud_{name}")
        im.crop((0, 640, 1920, 1080)).save(OUT / f"crop_town_hud_{name}.png")
        return 0

    if phase == "click_xy":
        nx, ny = float(sys.argv[2]), float(sys.argv[3])
        name = sys.argv[4] if len(sys.argv) > 4 else "town_click"
        click(pad, hwnd, nx, ny, wait=float(sys.argv[5]) if len(sys.argv) > 5 else 1.4)
        im = shot(hwnd, name)
        im.crop((0, 200, 1920, 1080)).save(OUT / f"crop_{name}.png")
        return 0

    if phase == "rclick_xy":
        nx, ny = float(sys.argv[2]), float(sys.argv[3])
        name = sys.argv[4] if len(sys.argv) > 4 else "town_rclick"
        rclick(pad, hwnd, nx, ny, wait=1.6)
        im = shot(hwnd, name)
        im.crop((400, 80, 1550, 980)).save(OUT / f"crop_{name}.png")
        return 0

    if phase == "treasury":
        name = sys.argv[2] if len(sys.argv) > 2 else "treasury"
        im = shot(hwnd, name)
        im.crop((1640, 0, 1920, 80)).save(OUT / f"crop_{name}.png")
        return 0

    if phase == "close_construct":
        click(pad, hwnd, *CONSTRUCT_CLOSE, wait=1.2)
        shot(hwnd, "town_after_construct_close")
        return 0

    if phase == "close_browser":
        click(pad, hwnd, *BROWSER_CLOSE, wait=1.3)
        shot(hwnd, "town_after_browser_close")
        return 0

    if phase == "close_x":
        if len(sys.argv) >= 4:
            x, y = float(sys.argv[2]), float(sys.argv[3])
        else:
            x, y = OVERVIEW_CLOSE
        click(pad, hwnd, x, y, wait=1.3)
        shot(hwnd, "town_after_close")
        return 0

    if phase == "lists":
        pad.chord_scancode("ctrl", "5", hwnd=hwnd)
        time.sleep(1.4)
        shot(hwnd, "town_lists")
        return 0

    raise SystemExit(f"unknown phase {phase}")


if __name__ == "__main__":
    raise SystemExit(main())
