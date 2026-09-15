"""Live: AO vision finds Julii army → CV finds Segesta → select → sword → war Yes.

**Prefer** ``scripts/accept_yolo_besiege_segesta.py`` (AO object_detection for
armies). This script keeps the older VL army-locate path for comparison.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import json
import re
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

ARMY_PROMPT = """This is a Total War: ROME REMASTERED campaign map screenshot.

Find FIELD ARMIES only — walking figures / generals with a vertical faction
banner beside them. Do NOT report settlements (round coloured plaque badges
or town ovals). Do NOT report ships. Do NOT report agents alone if they have
no army stack of soldiers.

Player faction banners are red with a gold laurel wreath (House of Julii).
Enemy/neutral field banners may be green or other colours.

For each field army report:
- colour: one word (red, green, ...)
- kind: "ours" if Julii red laurel, else "other"
- x: horizontal centre of the figure or banner, fraction of image width (0..1)
- y: vertical centre of the figure or banner, fraction of image height (0..1)

Reply with ONLY a JSON array. Example shape:
[{"colour":"red","kind":"ours","x":0.40,"y":0.50}]
Use [] if none. No prose.
"""


def _parse_armies(raw: str) -> list[dict]:
    text = (raw or "").strip()
    if not text:
        return []
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if not match:
            return []
        try:
            obj = json.loads(match.group(0))
        except json.JSONDecodeError:
            return []
    if not isinstance(obj, list):
        return []
    out: list[dict] = []
    for row in obj:
        if not isinstance(row, dict):
            continue
        try:
            x = float(row["x"])
            y = float(row["y"])
        except (KeyError, TypeError, ValueError):
            continue
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            continue
        kind = str(row.get("kind") or "").strip().lower()
        colour = str(row.get("colour") or row.get("color") or "").strip().lower()
        if not kind:
            kind = "ours" if colour == "red" else "other"
        out.append({"colour": colour, "kind": kind, "x": x, "y": y})
    return out


def main() -> int:
    from comstar_game_ai.agent.compositor.views import ViewBudget, compose_reach_images
    from comstar_game_ai.agent.reach.director import (
        MAP_TARGET_VISION,
        _bridge_direct_agent,
        _extract_text,
        _wait_ready,
    )
    from comstar_game_ai.agent.sync_deliberator import SyncCampaignDeliberator
    from comstar_game_ai.game_io.campaign.army import count_selected_unit_cards
    from comstar_game_ai.game_io.campaign.besiege_actuation import BesiegeActuator
    from comstar_game_ai.game_io.campaign.camera_pose import FrustumMeasure
    from comstar_game_ai.game_io.campaign.combat import (
        client_norm_to_screen,
        read_cursor_handle,
    )
    from comstar_game_ai.game_io.campaign.settlement_detector import detect_settlements
    from comstar_game_ai.game_io.campaign.ui_mode import grab_rgb_image
    from comstar_game_ai.game_io.input.send_input import SendInputController
    from comstar_game_ai.game_io.window import find_game_window
    from comstar_game_ai.shared.config import load_config
    from comstar_game_ai.shared.ipc.publisher import EventPublisher
    from comstar_game_ai.shared.runtime import ada_yield
    from comstar_game_ai.shared.runtime.directive_store import DirectiveStore

    print("CV+AO BESIEGE Segesta: army via AO vision, town via CV.", flush=True)
    for i in range(5, 0, -1):
        print(f"  going in {i}...", flush=True)
        time.sleep(1)
    print("GO", flush=True)

    cfg = load_config()
    vision = str((cfg.get("ao") or {}).get("vision_model") or "ollama/qwen3-vl:8b")
    faction = str((cfg.get("campaign") or {}).get("player_faction") or "julii")
    game = find_game_window(cfg["game"]["window_title_substrings"])
    if game is None:
        print("FAIL: no game window", flush=True)
        return 2
    hwnd = game.hwnd
    controller = SendInputController()
    controller.focus_window(hwnd)
    time.sleep(0.35)

    def grab():
        return grab_rgb_image(hwnd)

    frame = grab()
    if frame is None:
        print("FAIL: no frame", flush=True)
        return 2

    out = ROOT / "data" / "runtime" / "view_besiege"
    out.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    frame.convert("RGB").save(out / f"{stamp}_ao_army_frame.jpg", quality=90)

    # --- Segesta via CV badges ---
    bgr = cv2.cvtColor(np.array(frame.convert("RGB")), cv2.COLOR_RGB2BGR)
    h, w = bgr.shape[:2]
    hits = detect_settlements(bgr)
    greens = [d for d in hits if d["faction_colour"] == "green"]
    print(f"CV badges={len(hits)} green={len(greens)}", flush=True)
    if not greens:
        print("FAIL: no green settlement badge for Segesta", flush=True)
        return 1
    segesta = min(greens, key=lambda d: d["badge_px"][0])
    sbx, sby = segesta["badge_px"]
    print(
        f"Segesta CV badge px=({sbx},{sby}) norm=({sbx / w:.3f},{sby / h:.3f})",
        flush=True,
    )

    # --- Armies via AO vision ---
    log_path = out / f"ao_army_{stamp}.log"
    deliberator = SyncCampaignDeliberator(
        directive_store=DirectiveStore(),
        publisher=EventPublisher(),
        player_faction=faction,
        log_path=log_path,
    )
    print("starting AO deliberator...", flush=True)
    t0 = time.monotonic()
    deliberator.start(timeout_s=900.0)
    print(f"AO ready in {time.monotonic() - t0:.1f}s", flush=True)
    asyncio.run_coroutine_threadsafe(asyncio.sleep(0), deliberator._loop).result(timeout=10)
    time.sleep(0.4)

    images, _ = compose_reach_images(
        [frame],
        budget=ViewBudget(max_images=1, width=1280, height=720, jpeg_quality=85),
    )

    async def _army_call() -> str:
        session = deliberator._runtime.session
        assert session is not None
        text = ARMY_PROMPT
        if vision and not text.lstrip().lower().startswith("[model="):
            text = f"[model={vision}]\n{text}"
        await _wait_ready(session, MAP_TARGET_VISION)

        def _status(s: object) -> None:
            print(f"army-vision: {getattr(s, 'phase', None) or s}", flush=True)

        result = await _bridge_direct_agent(
            session.bridge,
            agent_provider_id=MAP_TARGET_VISION,
            text=text,
            context="",
            question_id="army-locate-field",
            priority="high",
            timeout=600.0,
            images=images,
            response_format=None,
            json_schema=None,
            on_status=_status,
        )
        return _extract_text(result)

    try:
        with ada_yield.held(holder="accept", reason="army_locate"):
            fut = asyncio.run_coroutine_threadsafe(_army_call(), deliberator._loop)
            deadline = time.monotonic() + 610.0
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    fut.cancel()
                    print("FAIL: army vision timeout", flush=True)
                    return 1
                try:
                    raw = fut.result(timeout=min(2.0, remaining))
                    break
                except concurrent.futures.TimeoutError:
                    continue
    except Exception as exc:
        print(f"FAIL army vision: {type(exc).__name__}: {exc}", flush=True)
        deliberator.stop(timeout_s=30.0)
        return 1

    (out / f"{stamp}_ao_army_raw.txt").write_text(raw or "", encoding="utf-8")
    print(f"army raw ({len(raw or '')} chars):\n{raw}", flush=True)
    armies = _parse_armies(raw or "")
    ours = [a for a in armies if a["kind"] == "ours" or a["colour"] == "red"]
    print(f"parsed armies={len(armies)} ours={len(ours)}", flush=True)
    for a in armies:
        print(f"  {a}", flush=True)

    if not ours:
        print("FAIL: AO found no Julii (red/ours) field army", flush=True)
        deliberator.stop(timeout_s=30.0)
        return 1

    # Prefer our army nearest Segesta badge.
    def _dist2(a: dict) -> float:
        return (a["x"] - sbx / w) ** 2 + (a["y"] - sby / h) ** 2

    army = min(ours, key=_dist2)
    print(
        f"select army nearest Segesta norm=({army['x']:.3f},{army['y']:.3f})",
        flush=True,
    )

    ann = frame.convert("RGB").copy()
    draw = ImageDraw.Draw(ann)
    draw.ellipse((sbx - 12, sby - 12, sbx + 12, sby + 12), outline=(0, 255, 0), width=3)
    axp, ayp = int(army["x"] * w), int(army["y"] * h)
    draw.ellipse((axp - 14, ayp - 14, axp + 14, ayp + 14), outline=(255, 80, 80), width=3)
    draw.text((axp + 16, ayp - 10), "ARMY", fill=(255, 80, 80))
    ann.save(out / f"{stamp}_ao_army_ann.jpg", quality=90)

    # Select army
    if not controller.click_client_norm(hwnd, army["x"], army["y"], dwell_ms=60):
        print("FAIL: army click failed", flush=True)
        deliberator.stop(timeout_s=30.0)
        return 1
    time.sleep(0.7)
    # Small nudge clicks around the reported point if cards still 0.
    cards = 0
    for ox, oy in [(0, 0), (0.01, 0), (-0.01, 0), (0, 0.015), (0, -0.015), (0.02, 0.02)]:
        nx = min(0.98, max(0.02, army["x"] + ox))
        ny = min(0.90, max(0.05, army["y"] + oy))
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
        return 1
    print(f"army selected cards={cards}", flush=True)

    # Stop AO before long hover/click so we do not hold Ada idle.
    try:
        deliberator.stop(timeout_s=30.0)
    except Exception as exc:
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
        print(f"probe Segesta offset=({dx},{dy}) norm=({nx:.3f},{ny:.3f})", flush=True)
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
            return 1
        used_offset = (dx, dy)
        click_norm = (nx, ny)
        for attempt in range(1, 6):
            time.sleep(0.55 if attempt == 1 else 0.4)
            modal = grab()
            if modal is not None:
                modal.convert("RGB").save(
                    out / f"{stamp}_modal_{attempt}.jpg", quality=90
                )
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
        print("FAIL: no sword on Segesta probes", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
