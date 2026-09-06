"""Walk army selection, family tree, bodyguard, and field construction.

Do not click Family Tree characters (sets the heir). Do not End Turn.
Field construction (fort / watchtower) needs a named general not in a town.
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

OVERVIEW_CLOSE = ui_atlas.OVERVIEW_FRAME.close_x
FINANCE_TAB = ui_atlas.OVERVIEW_TAB_CENTRES[3]
LISTS_MILITARY = (0.50, 0.259)
LISTS_LOCATE = (0.72, 0.52)
BODYGUARD = (0.120, 0.960)
TRAITS = (0.090, 0.960)


def shot(hwnd, name: str):
    image = ui_mode.grab_rgb_image(hwnd)
    image.save(OUT / f"{name}.png")
    print(
        f"{name}: panel={modal.panel_bounds(image)} "
        f"mode={ui_mode.classify_campaign_image(image).mode.value}"
    )
    return image


def hover(pad, hwnd, nx: float, ny: float, name: str, dwell: float = 1.4):
    left, top, right, bottom = win32gui.GetClientRect(hwnd)
    sx, sy = win32gui.ClientToScreen(
        hwnd, (int(round(nx * (right - left))), int(round(ny * (bottom - top))))
    )
    pad.move_mouse(sx, sy)
    time.sleep(0.12)
    pad.move_mouse(sx, sy)
    time.sleep(dwell)
    return shot(hwnd, name)


def click(pad, hwnd, nx: float, ny: float, wait: float = 1.2):
    pad.click_client_norm(hwnd, nx, ny)
    time.sleep(wait)


def rclick(pad, hwnd, nx: float, ny: float, wait: float = 1.5):
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
        shot(hwnd, "army_snap")
        return 0

    if phase == "close_x":
        if len(sys.argv) >= 4:
            click(pad, hwnd, float(sys.argv[2]), float(sys.argv[3]))
        else:
            click(pad, hwnd, *OVERVIEW_CLOSE)
        shot(hwnd, "army_after_close")
        return 0

    if phase == "lists_military":
        pad.chord_scancode("ctrl", "5", hwnd=hwnd)
        time.sleep(1.4)
        click(pad, hwnd, *LISTS_MILITARY, wait=1.2)
        im = shot(hwnd, "army_lists")
        im.crop((400, 120, 1500, 980)).save(OUT / "crop_army_lists.png")
        return 0

    if phase == "locate":
        click(pad, hwnd, *LISTS_LOCATE, wait=1.5)
        im = shot(hwnd, "army_located")
        im.crop((0, 640, 1920, 1080)).save(OUT / "crop_army_located.png")
        return 0

    if phase == "hover_xy":
        nx, ny = float(sys.argv[2]), float(sys.argv[3])
        name = sys.argv[4] if len(sys.argv) > 4 else "army_hover"
        im = hover(pad, hwnd, nx, ny, name)
        im.crop((200, 200, 1920, 1080)).save(OUT / f"crop_{name}.png")
        return 0

    if phase == "click_xy":
        nx, ny = float(sys.argv[2]), float(sys.argv[3])
        name = sys.argv[4] if len(sys.argv) > 4 else "army_click"
        click(pad, hwnd, nx, ny, wait=float(sys.argv[5]) if len(sys.argv) > 5 else 1.4)
        im = shot(hwnd, name)
        im.crop((0, 200, 1920, 1080)).save(OUT / f"crop_{name}.png")
        return 0

    if phase == "rclick_xy":
        nx, ny = float(sys.argv[2]), float(sys.argv[3])
        name = sys.argv[4] if len(sys.argv) > 4 else "army_rclick"
        rclick(pad, hwnd, nx, ny)
        im = shot(hwnd, name)
        im.crop((200, 80, 1700, 1000)).save(OUT / f"crop_{name}.png")
        return 0

    if phase == "bodyguard":
        click(pad, hwnd, *BODYGUARD, wait=1.5)
        im = shot(hwnd, "army_bodyguard")
        im.crop((400, 80, 1550, 980)).save(OUT / "crop_army_bodyguard.png")
        return 0

    if phase == "traits":
        click(pad, hwnd, *TRAITS, wait=1.5)
        im = shot(hwnd, "army_traits")
        im.crop((400, 80, 1550, 980)).save(OUT / "crop_army_traits.png")
        return 0

    if phase == "finance":
        pad.chord_scancode("ctrl", "4", hwnd=hwnd)
        time.sleep(1.5)
        im = shot(hwnd, "army_finance")
        im.crop((480, 120, 1450, 980)).save(OUT / "crop_army_finance.png")
        return 0

    if phase == "family_tree":
        # Family Tree sub-tab on Finance & Family. Hover first via hover_xy.
        nx, ny = (float(sys.argv[2]), float(sys.argv[3])) if len(sys.argv) > 3 else (0.42, 0.24)
        click(pad, hwnd, nx, ny, wait=1.4)
        im = shot(hwnd, "army_family_tree")
        im.crop((480, 120, 1450, 980)).save(OUT / "crop_army_family_tree.png")
        return 0

    raise SystemExit(f"unknown phase {phase}")


if __name__ == "__main__":
    raise SystemExit(main())
