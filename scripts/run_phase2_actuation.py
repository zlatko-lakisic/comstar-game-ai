#!/usr/bin/env python3
"""Live Phase 2 actuation acceptance — requires Rome on campaign map with telemetry mod."""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import time
from pathlib import Path

from comstar_game_ai.game_io.campaign.ui_mode import CampaignUiMode, grab_and_classify
from comstar_game_ai.game_io.drivers.hardcoded_campaign import HardcodedCampaignDriver, phase2_accepted
from comstar_game_ai.game_io.elevation import (
    ensure_elevation_for_game,
    strip_elevation_marker,
    tee_output,
    trail_path_from_argv,
)
from comstar_game_ai.game_io.logs.telemetry_health import telemetry_health
from comstar_game_ai.game_io.state_machine import GameState
from comstar_game_ai.game_io.window import find_game_window
from comstar_game_ai.shared.config import load_config
from comstar_game_ai.shared.ipc.events import EventKind
from comstar_game_ai.shared.ipc.publisher import EventPublisher
from comstar_game_ai.shared.runtime.directive_store import DirectiveStore


def _overlay_listening(host: str, port: int, timeout: float = 0.4) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(timeout)
        return probe.connect_ex((host, port)) == 0


def _start_overlay(host: str, port: int, *, wait_s: float = 12.0) -> subprocess.Popen | None:
    """Bring up Process C, or attach to the one already running.

    Returns the process only when this script started it, so an overlay the operator
    launched by hand is left running when the acceptance run ends.
    """
    if _overlay_listening(host, port):
        print("OK  overlay already listening — attaching to it")
        return None

    proc = subprocess.Popen([sys.executable, "-m", "comstar_game_ai.overlay_ui.main"])
    deadline = time.time() + wait_s
    while time.time() < deadline:
        if proc.poll() is not None:
            print(f"WARN overlay exited immediately (code {proc.returncode}) — running without it")
            return None
        if _overlay_listening(host, port):
            print(f"OK  overlay up (pid {proc.pid})")
            return proc
        time.sleep(0.4)
    print("WARN overlay did not start listening — running without it")
    return proc


def _stop_overlay(proc: subprocess.Popen | None) -> None:
    """Close an overlay this script started. One that was already up is left alone."""
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    print("OK  overlay closed")


def _start_deliberation(interval_s: float, log_path: Path) -> subprocess.Popen | None:
    """Bring up Process B beside this run so one command puts AO in the loop.

    Its output goes to its own file rather than this console: model chatter
    interleaved with the turn trail makes both unreadable, and the trail is the
    thing an operator watches during a live run.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handle = log_path.open("w", encoding="utf-8")
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "comstar_game_ai.agent.main",
            "--deliberate-loop",
            "--interval",
            str(interval_s),
        ],
        stdout=handle,
        stderr=subprocess.STDOUT,
    )
    print(f"OK  deliberation started (pid {proc.pid}) — log: {log_path}")
    return proc


def _stop_deliberation(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    print("OK  deliberation stopped")


def _wait_for_first_directive(
    store: DirectiveStore, *, newer_than: float, timeout_s: float
) -> bool:
    """Whether Process B has written a directive of its own during this run.

    A file left by an earlier session does not count. Without this check a dead AO
    is indistinguishable from a thoughtful one: the driver would read hold every
    turn and the campaign would sit still for twenty turns before anyone noticed.
    """
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        stored = store.read()
        if stored is not None and float(stored.ts or 0.0) >= newer_than:
            return True
        time.sleep(1.0)
    return False


def _countdown(seconds: int) -> None:
    if seconds <= 0:
        return
    print(f"INFO click Rome and leave it focused — starting in {seconds}s", flush=True)
    for remaining in range(seconds, 0, -1):
        print(f"  {remaining}...", flush=True)
        time.sleep(1)
    print("INFO starting", flush=True)


def main() -> int:
    raw_argv = list(sys.argv)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    trail = trail_path_from_argv() or str(
        Path(f"data/runtime/phase2_live_{stamp}.log").resolve()
    )
    tee_output(trail)
    sys.argv = [sys.argv[0], *strip_elevation_marker()]

    parser = argparse.ArgumentParser(description="Phase 2 live actuation")
    parser.add_argument(
        "--seconds",
        type=int,
        default=8,
        help="Countdown before first key/click so you can focus Rome (default 8; 0 skips)",
    )
    parser.add_argument(
        "--no-overlay",
        dest="overlay",
        action="store_false",
        help="do not start the operator overlay, and publish no events to it",
    )
    parser.set_defaults(overlay=True)
    parser.add_argument(
        "--directives",
        dest="directives",
        action="store_true",
        default=None,
        help="put AO in the loop: start Process B and plan each turn from its directive",
    )
    parser.add_argument(
        "--no-directives",
        dest="directives",
        action="store_false",
        help="ignore any directive on disk and plan from the loop's own policy",
    )
    parser.add_argument(
        "--allow-blind",
        action="store_true",
        help="run even when Rome's logs are off, i.e. with no telemetry and no belief",
    )
    parser.add_argument(
        "--deliberate-interval",
        type=float,
        default=45.0,
        help="Seconds between AO directives with --directives (default 45)",
    )
    args = parser.parse_args()

    cfg = load_config()
    subs = cfg.get("game", {}).get("window_title_substrings", ["Rome"])
    game = find_game_window(subs)
    if game is None:
        print("FAIL: Rome window not found — launch game and load Julii campaign first")
        return 1

    print(f"OK  game_window: {game.title!r} {game.width}x{game.height}")
    print(f"OK  trail: {trail}")

    # Before elevation and before any input: a Rome launched by hand has its logs off,
    # and nothing inside the game reveals that. Turns still advance, so the run looks
    # healthy for twenty minutes and ends with an empty belief store.
    health = telemetry_health()
    print(f"{'OK ' if health.ok else 'WARN'} {health.summary}")
    if not health.ok and not args.allow_blind:
        print(
            "FAIL: telemetry is off, so this run would drive the campaign blind — no "
            "characters, no settlements, no record of what changed. Relaunch with "
            "scripts/launch_rome.ps1 (it passes -enable_logging "
            "-verbose_script_logging), or re-run with --allow-blind to accept it."
        )
        return 1

    import win32process

    _, pid = win32process.GetWindowThreadProcessId(game.hwnd)
    action = ensure_elevation_for_game(pid, argv=raw_argv, log_path=trail)
    if action == "relaunching":
        print("INFO approve UAC — a new 'Comstar Game AI' window will show the live trail", flush=True)
        print("INFO click Rome during the countdown in that window", flush=True)
        return 0
    if action == "failed":
        return 1

    turns = int(cfg.get("campaign", {}).get("acceptance_turns", 20))
    faction = cfg.get("campaign", {}).get("player_faction", "julii")
    auto_end = bool(cfg.get("campaign", {}).get("auto_end_turn", True))
    ready_timeout = float(cfg.get("campaign", {}).get("end_turn_ready_timeout_s", 30))
    legacy_delay = float(cfg.get("campaign", {}).get("end_turn_delay_s", 0))

    combat_cfg = (cfg.get("campaign", {}).get("combat") or {})
    row = combat_cfg.get("army_lists_row_norm")
    targets = combat_cfg.get("attack_targets") or []

    directive_cfg = (cfg.get("campaign", {}).get("directive") or {})
    # The flag wins over config so a single command can put AO in the loop without
    # editing YAML, and --no-directives can take it back out for a comparison run.
    directives_on = (
        bool(directive_cfg.get("enabled")) if args.directives is None else args.directives
    )
    directive_max_age_s = float(directive_cfg.get("max_age_s", 900))
    directive_store = DirectiveStore(directive_cfg.get("path")) if directives_on else None

    driver = HardcodedCampaignDriver(
        player_faction=faction,
        use_vision=True,
        auto_end_turn=auto_end,
        end_turn_ready_timeout_s=ready_timeout,
        end_turn_delay_s=legacy_delay,
        auto_resolve_battles=bool(combat_cfg.get("auto_resolve_battles", True)),
        attack_enabled=bool(combat_cfg.get("attack_enabled", False)),
        army_lists_row_norm=(float(row[0]), float(row[1])) if row else None,
        attack_targets=tuple((float(t[0]), float(t[1])) for t in targets),
        directive_store=directive_store,
        directive_max_age_s=directive_max_age_s,
    )
    print(
        f"INFO combat: auto_resolve={driver.auto_resolve_battles} "
        f"attack={driver.attack_enabled} targets={len(driver.attack_targets)} "
        f"lists_row={driver.army_lists_row_norm}"
    )
    if directive_store is None:
        print("INFO directives: off — the loop plans from its own policy")
    else:
        print(f"INFO directives: reading {directive_store.path}")
    ingested = driver.bootstrap_from_logs()
    print(f"INFO bootstrap_from_logs: {ingested} records")
    print(
        f"INFO state after bootstrap: {driver.state.state.value} turn={driver.state.turn} "
        f"turns_seen={driver._julii_turns_seen}"
    )

    def on_progress(*, index: int, total: int, phase: str, ok: bool | None = None) -> None:
        tag = f"ATTEMPT {index}/{total} game_turn={driver._known_game_turn()}"
        if ok is None:
            print(f"{tag}  {phase}", flush=True)
        else:
            print(f"{tag}  {'OK' if ok else 'FAIL'}  {phase}", flush=True)

    print(
        f"INFO running {turns} attempts (vision dismiss + observe + End Turn on readiness)...",
        flush=True,
    )

    # Started before the countdown, so the surfaces are up over the game while the
    # operator is still looking at it, and a broken overlay is obvious before any
    # input is injected.
    overlay_proc = None
    if args.overlay:
        ipc = cfg.get("ipc") or {}
        host = ipc.get("event_socket_host", "127.0.0.1")
        port = int(ipc.get("event_socket_port", 9876))
        overlay_proc = _start_overlay(host, port)
        if _overlay_listening(host, port):
            publisher = EventPublisher(host=host, port=port)
            publisher.publish(EventKind.CONTROL_STATE, {"state": "idle"})
            driver.publisher = publisher
            print(f"OK  publishing overlay events to {host}:{port}")
        else:
            print("INFO no overlay listening — the run publishes nothing")

    # Also before the countdown: AO's first call has to reach ada and come back, so
    # the seconds the operator spends focusing Rome are the warm-up.
    deliberation_proc = None
    directives_started_at = time.time()
    if directive_store is not None:
        deliberation_proc = _start_deliberation(
            args.deliberate_interval,
            Path(f"data/runtime/deliberate_{stamp}.log"),
        )

    _countdown(max(0, args.seconds))

    if directive_store is not None:
        # A stale file on disk is not evidence that anyone is thinking, so this waits
        # for a directive written since Process B came up. If none arrives, the run
        # continues on the loop's own policy: twenty turns of standing still because
        # ada was unreachable is a worse outcome than twenty turns without AO.
        if _wait_for_first_directive(
            directive_store, newer_than=directives_started_at, timeout_s=90.0
        ):
            print(f"OK  first directive in: {driver.current_directive().intent.objective}")
        else:
            alive = deliberation_proc is not None and deliberation_proc.poll() is None
            print(
                "WARN no directive after 90s "
                f"({'Process B still running' if alive else 'Process B exited'}) — "
                "continuing on the loop's own policy. Check the deliberate log; "
                "ada may be down or llama3.1:8b not pulled."
            )
            driver.directive_store = None
            directive_store = None

    # Classify only after the countdown. Before it, Rome may not be focused and the
    # operator has not had their chance to clear the screen, so an early look judged a
    # campaign by whatever happened to be on it and refused to start.
    driver.poll_observation()
    if not driver.state.allows_campaign_orders():
        # Rome rewrites message_log.txt on launch and buffers its writes, so a campaign
        # just entered has flushed nothing to read yet — a fresh campaign sitting on
        # turn 1 leaves the log silent. Vision is the only evidence available there.
        classification = grab_and_classify(game.hwnd)
        print(
            f"INFO log gate inconclusive (state={driver.state.state.value}, "
            f"turn={driver.state.turn}); vision says {classification.mode.value} "
            f"({classification.detail}, confidence {classification.confidence:.2f})",
            flush=True,
        )
        # A panel with the map behind it still means we are in a campaign, and clearing
        # panels is the loop's job — refusing to start over a senate notice card is a
        # worse failure than dismissing it. A full-parchment screen could be the front
        # end, so that one is not accepted here.
        map_is_behind = classification.detail in ("left_overlay_panel", "panel_over_centre")
        if classification.mode is CampaignUiMode.CAMPAIGN_MAP or (
            classification.mode is CampaignUiMode.MODAL and map_is_behind
        ):
            driver.state.state = GameState.CAMPAIGN_MAP
        else:
            print(
                "FAIL: not on campaign map — neither the log nor the screen shows the "
                "strat map. Load or start a campaign, wait for the map, then re-run."
            )
            _stop_overlay(overlay_proc)
            _stop_deliberation(deliberation_proc)
            return 1

    try:
        result = driver.run_turns(
            turns,
            require_ok=False,
            wait_for_next_turn=True,
            on_progress=on_progress,
        )
    except BaseException:
        # Ctrl+C and the kill switch included: a stranded overlay sits on top of
        # every other window, and a stranded Process B keeps talking to ada, so
        # neither may survive an abandoned run.
        _stop_overlay(overlay_proc)
        _stop_deliberation(deliberation_proc)
        raise

    print(
        f"{'OK' if result['desyncs'] == 0 else 'WARN'}  turns_ok={result['turns_ok']} "
        f"turns_failed={result['turns_failed']} desyncs={result['desyncs']}"
    )
    resets = result.get("turn_baseline_resets", 0)
    print(
        f"OK  campaign advanced {result['turns_advanced']} turns "
        f"(endpoints seen: {result['game_turn_start']} -> {result['game_turn_end']})"
    )
    if resets:
        print(
            f"INFO turn baseline re-read {resets}x — Rome's saves folder still holds an "
            "earlier campaign, so the endpoints above are not a measure of this run"
        )
    print(
        f"OK  belief_history={len(driver.belief.history)} armies={len(driver.belief.armies)} "
        f"settlements={len(driver.belief.settlements)}"
    )
    print(
        f"OK  attacks_ordered={result['attacks_ordered']} "
        f"battles_auto_resolved={result['battles_resolved']}"
    )
    if driver.directive_store is not None:
        print(f"OK  last directive: {driver.last_directive or 'none read'}")

    report = {
        "game": {"title": game.title, "rect": game.rect},
        "turns": result,
        "directives": {
            "enabled": driver.directive_store is not None,
            "last": driver.last_directive,
        },
        "state": driver.state.state.value,
        "belief_history_len": len(driver.belief.history),
        "intent_log": str(driver.intent_writer.path),
    }
    out = Path("data/runtime/phase2_report.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"OK  report: {out}")

    # Left up through the run and the report, so the last state is still on screen
    # while the numbers print. Only closed if this script started it.
    _stop_overlay(overlay_proc)
    _stop_deliberation(deliberation_proc)

    if phase2_accepted(result, turns=turns):
        print(f"\nPASS Phase 2 actuation ({turns} turns, zero desyncs)")
        return 0

    if result["turns_ok"] >= turns and result["turns_advanced"] < turns:
        print(
            f"\nFAIL Phase 2 — {result['turns_ok']} cycles reported OK but the campaign "
            f"advanced {result['turns_advanced']} turns. Turn detection is over-counting."
        )
        return 1

    if result["turns_advanced"] > 0:
        print("\nPARTIAL Phase 2 — some turns succeeded; check intent log and Rome console focus")
        return 0

    print("\nFAIL Phase 2 — no turns completed")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
