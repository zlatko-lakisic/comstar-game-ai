"""Walk overlay layers and the faction-summary tab strip from the HUD buttons."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import win32gui

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from comstar_game_ai.game_io.campaign import modal, ui_atlas, ui_mode
from comstar_game_ai.game_io.input.send_input import SendInputController
from comstar_game_ai.game_io.window import find_game_window
from comstar_game_ai.shared.config import load_config

OUT = ROOT / "data/runtime/sweep"

# Icon centres for the 12 overlay layer buttons (not their tick boxes).
OVERLAY_LAYERS = [
    (0.2710, 0.952),
    (0.3075, 0.952),
    (0.3440, 0.952),
    (0.3805, 0.952),
    (0.4170, 0.952),
    (0.4535, 0.952),
    (0.4900, 0.952),
    (0.5265, 0.952),
    (0.5630, 0.952),
    (0.5995, 0.952),
    (0.6360, 0.952),
    (0.6725, 0.952),
]


def shot(hwnd, name: str):
    image = ui_mode.grab_rgb_image(hwnd)
    image.save(OUT / f"{name}.png")
    print(f"{name}: panel={modal.panel_bounds(image)} mode={ui_mode.classify_campaign_image(image).mode.value}")
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


def main() -> int:
    phase = sys.argv[1] if len(sys.argv) > 1 else "layers"
    cfg = load_config()
    hwnd = find_game_window(cfg.get("game", {}).get("window_title_substrings", ["Rome"])).hwnd
    pad = SendInputController()
    pad.focus_window(hwnd)
    time.sleep(0.35)

    if phase == "layers":
        for i, (x, y) in enumerate(OVERLAY_LAYERS, start=1):
            click(pad, hwnd, x, y)
            im = shot(hwnd, f"ovl_click_{i:02d}")
            im.crop((0, 330, 300, 1080)).save(OUT / f"crop_legend_{i:02d}.png")
            im.crop((400, 780, 1520, 1080)).save(OUT / f"crop_bar_{i:02d}.png")
        return 0

    if phase == "close_escape":
        pad.tap_key("escape", hwnd=hwnd)
        time.sleep(1.2)
        shot(hwnd, "ovl_after_escape")
        return 0

    if phase == "close_eye":
        # Reopen via the eye, then close via the eye.
        click(pad, hwnd, 0.984, 0.030, wait=1.6)
        shot(hwnd, "ovl_reopened_eye")
        click(pad, hwnd, 0.984, 0.030, wait=1.6)
        shot(hwnd, "ovl_after_eye_toggle")
        return 0

    if phase == "faction":
        hover(pad, hwnd, 0.026, 0.957, "hud_hover_faction_std")
        click(pad, hwnd, 0.026, 0.957, wait=1.6)
        shot(hwnd, "hud_faction_open")
        # Walk the seven top-of-dialog tab crests.
        for i, (x, y) in enumerate(ui_atlas.OVERVIEW_TAB_CENTRES, start=1):
            click(pad, hwnd, x, y, wait=1.25)
            im = shot(hwnd, f"fs_tab_{i}")
            im.crop((480, 120, 1450, 980)).save(OUT / f"crop_fs_tab_{i}.png")
        return 0

    if phase == "faction_subs":
        # On the currently open overview tab, click likely sub-tab labels.
        # Factions tab (3) has Ranking / Diplomatic Standing near the top of the body.
        for name, x, y in (
            ("sub_rank", 0.33, 0.24),
            ("sub_diplo", 0.42, 0.24),
            ("sub_left2", 0.36, 0.24),
            ("sub_right2", 0.50, 0.24),
        ):
            click(pad, hwnd, x, y, wait=1.1)
            im = shot(hwnd, f"fs_{name}")
            im.crop((480, 120, 1450, 980)).save(OUT / f"crop_fs_{name}.png")
        return 0

    if phase == "close_x":
        x, y = ui_atlas.OVERVIEW_FRAME.close_x
        click(pad, hwnd, x, y, wait=1.3)
        shot(hwnd, "fs_after_close_x")
        return 0

    if phase == "reopen_escape_close":
        click(pad, hwnd, 0.026, 0.957, wait=1.6)
        shot(hwnd, "fs_reopened")
        pad.tap_key("escape", hwnd=hwnd)
        time.sleep(1.2)
        shot(hwnd, "fs_after_escape")
        return 0

    # Four gold/red category discs down the left edge. Pixel-centred from
    # dock_after_resume.png; hover first so we get official tooltips before clicking.
    DOCK_ICONS = (
        (0.0130, 0.1315),
        (0.0130, 0.2056),
        (0.0130, 0.2685),
        (0.0130, 0.3213),
    )

    if phase == "dock_hover":
        shot(hwnd, "dock_hover_base")
        for i, (x, y) in enumerate(DOCK_ICONS, start=1):
            im = hover(pad, hwnd, x, y, f"dock_hover_{i}")
            im.crop((0, 0, 520, 700)).save(OUT / f"crop_dock_hover_{i}.png")
        # Park the cursor away so a leftover tooltip is not mistaken for chrome.
        hover(pad, hwnd, 0.50, 0.50, "dock_hover_parked", dwell=0.4)
        return 0

    if phase == "dock_open":
        index = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        x, y = DOCK_ICONS[index - 1]
        click(pad, hwnd, x, y, wait=1.4)
        im = shot(hwnd, f"dock_open_{index}")
        im.crop((0, 0, 780, 1080)).save(OUT / f"crop_dock_open_{index}.png")
        return 0

    if phase == "dock_close_x":
        # Measured on the open Alerts dock: close X sits on the parchment corner.
        nx = float(sys.argv[2]) if len(sys.argv) > 2 else 0.160
        ny = float(sys.argv[3]) if len(sys.argv) > 3 else 0.077
        click(pad, hwnd, nx, ny, wait=1.3)
        shot(hwnd, "dock_after_close_x")
        return 0

    # When the dock is open the four category tabs ride the parchment's right
    # edge (panel right ~0.163). Closed-state y centres still hold.
    DOCK_TABS_OPEN = (
        (0.172, 0.1315),
        (0.172, 0.2056),
        (0.172, 0.2685),
        (0.172, 0.3213),
    )

    if phase == "dock_walk":
        base = shot(hwnd, "dock_walk_base")
        if modal.panel_bounds(base) is None:
            click(pad, hwnd, *DOCK_ICONS[0], wait=1.3)
            shot(hwnd, "dock_walk_opened")
        for i, (x, y) in enumerate(DOCK_TABS_OPEN, start=1):
            im = hover(pad, hwnd, x, y, f"dock_tab_hover_{i}")
            im.crop((0, 0, 720, 900)).save(OUT / f"crop_dock_tab_hover_{i}.png")
        for i, (x, y) in enumerate(DOCK_TABS_OPEN, start=1):
            click(pad, hwnd, x, y, wait=1.25)
            im = shot(hwnd, f"dock_tab_open_{i}")
            im.crop((0, 0, 780, 1080)).save(OUT / f"crop_dock_tab_open_{i}.png")
        # Chrome: filter (left of close X) then the two footer discs.
        for name, x, y in (
            ("filter", 0.138, 0.077),
            ("footer_left", 0.055, 0.88),
            ("footer_right", 0.105, 0.88),
        ):
            im = hover(pad, hwnd, x, y, f"dock_chrome_{name}")
            im.crop((0, 0, 720, 1080)).save(OUT / f"crop_dock_chrome_{name}.png")
        click(pad, hwnd, 0.160, 0.077, wait=1.3)
        shot(hwnd, "dock_walk_after_close_x")
        return 0

    if phase == "dock_switch":
        # Reopen from the collapsed left-edge horn. Do not click the already
        # selected Alerts tab — that click toggles the dock shut.
        click(pad, hwnd, *DOCK_ICONS[0], wait=1.35)
        shot(hwnd, "dock_switch_opened")
        for i in (2, 3, 4):
            x, y = DOCK_TABS_OPEN[i - 1]
            click(pad, hwnd, x, y, wait=1.35)
            im = shot(hwnd, f"dock_switch_{i}")
            im.crop((0, 0, 780, 1080)).save(OUT / f"crop_dock_switch_{i}.png")
        for name, x, y in (
            ("filter", 0.138, 0.077),
            ("footer_left", 0.070, 0.52),
            ("footer_right", 0.110, 0.52),
        ):
            im = hover(pad, hwnd, x, y, f"dock_switch_chrome_{name}")
            im.crop((0, 0, 780, 1080)).save(OUT / f"crop_dock_switch_chrome_{name}.png")
        click(pad, hwnd, 0.160, 0.077, wait=1.3)
        shot(hwnd, "dock_switch_after_close_x")
        return 0

    if phase == "dock_chrome":
        click(pad, hwnd, *DOCK_ICONS[0], wait=1.3)
        shot(hwnd, "dock_chrome_opened")
        for name, x, y in (
            ("filter", 0.148, 0.082),
            ("footer_burn", 0.065, 0.50),
            ("footer_hand", 0.105, 0.50),
        ):
            im = hover(pad, hwnd, x, y, f"dock_chrome2_{name}", dwell=1.5)
            im.crop((0, 40, 500, 620)).save(OUT / f"crop_dock_chrome2_{name}.png")
        click(pad, hwnd, 0.160, 0.077, wait=1.2)
        shot(hwnd, "dock_chrome_closed")
        return 0

    if phase == "dock_escape":
        click(pad, hwnd, *DOCK_ICONS[0], wait=1.3)
        shot(hwnd, "dock_esc_open")
        pad.tap_key("escape", hwnd=hwnd)
        time.sleep(1.2)
        im = shot(hwnd, "dock_esc_after")
        # If Escape paused the game, Return to Game is the first menu item.
        if modal.panel_bounds(im) is None and ui_mode.classify_campaign_image(im).mode.value != "campaign_map":
            click(pad, hwnd, 0.18, 0.28, wait=1.3)
            shot(hwnd, "dock_esc_resumed")
        elif modal.panel_bounds(im) is not None:
            # Dock still open: close via X so we do not leave it up.
            click(pad, hwnd, 0.160, 0.077, wait=1.2)
            shot(hwnd, "dock_esc_closed_x")
        return 0

    raise SystemExit(f"unknown phase {phase}")


if __name__ == "__main__":
    raise SystemExit(main())
