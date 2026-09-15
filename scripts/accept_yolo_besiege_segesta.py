"""Live: AO YOLO detection finds army → CV finds settlement → select → sword → war Yes.

Army locate uses ``client.detect_rtw_campaign`` (falls back to COCO nano smoke).
Settlement click uses OpenCV badge detect + offset probes. No VL coordinates.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

_OFFSETS_PX: list[tuple[int, int]] = [
    (10, 14),
    (14, 18),
    (18, 22),
    (22, 26),
    (12, 28),
    (26, 22),
    (8, 20),
    (30, 28),
    (16, 34),
    (34, 32),
    (40, 36),
    (20, 40),
    (0, 18),
]


def main() -> int:
    from comstar_game_ai.agent.reach.director import DETECT_RTW_CAMPAIGN, DETECT_YOLOX_NANO
    from comstar_game_ai.agent.sync_deliberator import SyncCampaignDeliberator
    from comstar_game_ai.game_io.campaign.army import count_selected_unit_cards
    from comstar_game_ai.game_io.campaign.besiege_actuation import BesiegeActuator
    from comstar_game_ai.game_io.campaign.camera_pose import FrustumMeasure
    from comstar_game_ai.game_io.campaign.combat import (
        client_norm_to_screen,
        read_cursor_handle,
    )
    from comstar_game_ai.game_io.campaign.map_object_detection import (
        armies_and_ships,
        nearest,
    )
    from comstar_game_ai.game_io.campaign.settlement_detector import detect_settlements
    from comstar_game_ai.game_io.campaign.ui_mode import grab_rgb_image
    from comstar_game_ai.game_io.input.send_input import SendInputController
    from comstar_game_ai.game_io.window import find_game_window
    from comstar_game_ai.shared.config import load_config
    from comstar_game_ai.shared.ipc.publisher import EventPublisher
    from comstar_game_ai.shared.runtime import ada_yield
    from comstar_game_ai.shared.runtime.directive_store import DirectiveStore

    cfg = load_config()
    ao = cfg.get("ao") or {}
    agent_id = str(
        ao.get("detection_rtw_agent") or DETECT_RTW_CAMPAIGN
    ).strip()

    subs = cfg.get("game", {}).get("window_title_substrings") or ["Rome"]
    game = find_game_window(subs)
    if game is None:
        print("FAIL: Rome window not found", flush=True)
        return 2

    hwnd = game.hwnd
    controller = SendInputController()
    controller.focus_window(hwnd)
    time.sleep(0.4)

    def grab():
        return grab_rgb_image(hwnd)

    frame = grab()
    if frame is None:
        print("FAIL: no frame", flush=True)
        return 2

    out = ROOT / "data" / "runtime" / "view_besiege"
    out.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    frame.convert("RGB").save(out / f"{stamp}_yolo_army_frame.jpg", quality=90)

    bgr = cv2.cvtColor(np.array(frame.convert("RGB")), cv2.COLOR_RGB2BGR)
    settlements = detect_settlements(bgr)
    print(f"CV settlements={len(settlements)}", flush=True)
    if not settlements:
        print("FAIL: no CV settlements", flush=True)
        return 3
    target = next((s for s in settlements if s.get("faction_colour") == "green"), settlements[0])
    sbx, sby = int(target["badge_px"][0]), int(target["badge_px"][1])
    w, h = frame.size
    print(f"CV target colour={target.get('faction_colour')} badge=({sbx},{sby})", flush=True)

    faction = str((cfg.get("campaign") or {}).get("player_faction") or "julii")
    deliberator = SyncCampaignDeliberator(
        directive_store=DirectiveStore(),
        publisher=EventPublisher(),
        player_faction=faction,
        log_path=out / f"yolo_army_{stamp}.log",
    )
    print("starting AO deliberator...", flush=True)
    try:
        deliberator.start(timeout_s=900.0)
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: AO session start: {exc}", flush=True)
        return 2
    print("AO ready", flush=True)

    try:
        with ada_yield.held(holder="accept", reason="yolo_army"):
            try:
                result = deliberator.query_object_detection(
                    frame,
                    agent_provider_id=agent_id,
                    timeout_s=180.0,
                    question_id=f"yolo-army-{stamp}",
                )
            except Exception:
                print(f"RTW agent failed; retrying {DETECT_YOLOX_NANO}", flush=True)
                result = deliberator.query_object_detection(
                    frame,
                    agent_provider_id=DETECT_YOLOX_NANO,
                    timeout_s=180.0,
                    question_id=f"yolo-army-smoke-{stamp}",
                )
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL detect: {type(exc).__name__}: {exc}", flush=True)
        deliberator.stop(timeout_s=30.0)
        return 5

    (out / f"{stamp}_yolo_army_raw.txt").write_text(result.raw_text or "", encoding="utf-8")
    units = armies_and_ships(result, include_ships=False)
    print(
        f"detect provider={result.provider_id or agent_id} "
        f"all={len(result.detections)} armies={len(units)} ms={result.inference_ms}",
        flush=True,
    )
    for d in result.detections:
        print(f"  {d.label} {d.score:.3f} {d.box_xyxy}", flush=True)

    if not units:
        print(
            "FAIL: no army_stack detections "
            "(publish trained client.detect_rtw_campaign weights first)",
            flush=True,
        )
        deliberator.stop(timeout_s=30.0)
        return 6

    army = nearest(units, x=float(sbx), y=float(sby), pixel_space=True)
    assert army is not None
    ax, ay = army.centre_norm(w, h)
    print(f"select army nearest badge norm=({ax:.3f},{ay:.3f})", flush=True)

    ann = frame.convert("RGB").copy()
    draw = ImageDraw.Draw(ann)
    draw.ellipse((sbx - 12, sby - 12, sbx + 12, sby + 12), outline=(0, 255, 0), width=3)
    for d in result.detections:
        x1, y1, x2, y2 = d.box_xyxy
        color = (255, 80, 80) if d is army else (80, 255, 80)
        draw.rectangle([x1, y1, x2, y2], outline=color, width=2)
    ann.save(out / f"{stamp}_yolo_army_ann.jpg", quality=90)

    if not controller.click_client_norm(hwnd, ax, ay, dwell_ms=60):
        print("FAIL: army click failed", flush=True)
        deliberator.stop(timeout_s=30.0)
        return 7
    time.sleep(0.7)
    cards = 0
    for ox, oy in [(0, 0), (0.01, 0), (-0.01, 0), (0, 0.015), (0, -0.015), (0.02, 0.02)]:
        nx = min(0.98, max(0.02, ax + ox))
        ny = min(0.90, max(0.05, ay + oy))
        controller.click_client_norm(hwnd, nx, ny, dwell_ms=50)
        time.sleep(0.55)
        check = grab()
        if check is None:
            continue
        cards = count_selected_unit_cards(check)
        print(f"  select nudge ({ox},{oy}) cards={cards}", flush=True)
        if cards >= 1:
            break
    if cards < 1:
        print("FAIL: army click did not produce unit cards", flush=True)
        deliberator.stop(timeout_s=30.0)
        return 8
    print(f"army selected cards={cards}", flush=True)

    try:
        deliberator.stop(timeout_s=30.0)
    except Exception as exc:  # noqa: BLE001
        print(f"WARN stop: {exc}", flush=True)

    actuator = BesiegeActuator(
        hwnd=hwnd,
        controller=controller,
        capture=grab,
        hover_dwell_s=1.1,
        sleep=time.sleep,
    )
    actuator.measure_frustum = lambda image=None: FrustumMeasure((0, 0), (1, 1))  # type: ignore

    baseline = read_cursor_handle()
    print(f"cursor baseline={baseline}", flush=True)

    ordered = False
    war_confirmed = False
    used_offset = None
    click_norm = None

    for dx, dy in _OFFSETS_PX:
        cx, cy = sbx + dx, sby + dy
        if not (0 <= cx < w and 0 <= cy < h):
            continue
        nx, ny = cx / w, cy / h
        print(f"probe settlement offset=({dx},{dy}) norm=({nx:.3f},{ny:.3f})", flush=True)
        screen = client_norm_to_screen(hwnd, nx, ny)
        if screen is None:
            continue
        controller.move_mouse(*screen)
        time.sleep(0.15)
        controller.move_mouse(*screen)
        time.sleep(1.1)
        hovered = read_cursor_handle()
        if hovered == 0 or hovered == baseline:
            print(f"  no sword cursor={hovered}", flush=True)
            continue
        print(f"  SWORD cursor={hovered} — right-click", flush=True)
        right = getattr(controller, "right_click_client_norm", None)
        if not callable(right) or not right(hwnd, nx, ny, dwell_ms=80):
            print("  right-click failed", flush=True)
            return 9
        used_offset = (dx, dy)
        click_norm = (nx, ny)
        for attempt in range(1, 6):
            time.sleep(0.55 if attempt == 1 else 0.4)
            modal = grab()
            if modal is not None:
                modal.convert("RGB").save(out / f"{stamp}_modal_{attempt}.jpg", quality=90)
            war_confirmed = actuator.confirm_declare_war(owner_raw="gaul")
            print(f"  war_yes attempt {attempt}={war_confirmed}", flush=True)
            if war_confirmed:
                break
        after = grab()
        if after is not None:
            after.convert("RGB").save(out / f"{stamp}_after.jpg", quality=90)
        ordered = True
        break

    print(
        f"RESULT ordered={ordered} war_confirmed={war_confirmed} "
        f"click={click_norm} offset={used_offset}",
        flush=True,
    )
    if not ordered:
        print("FAIL: no sword on settlement probes", flush=True)
        return 10
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
