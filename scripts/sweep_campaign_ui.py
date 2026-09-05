#!/usr/bin/env python3
"""Guided sweep: open each campaign panel on purpose and measure it.

The atlas knows 19 panels because the string tables and the binding database name
them, but only the handful our failure corpus happened to contain has measured
geometry. Waiting for the rest to appear by chance is what left them UNSEEN. This
opens each one deliberately via its own hotkey, captures it, measures the panel and
its close button, then puts the screen back the way it found it.

    python scripts/sweep_campaign_ui.py --dry-run       # show the plan, touch nothing
    python scripts/sweep_campaign_ui.py                 # sweep every hotkey panel
    python scripts/sweep_campaign_ui.py --only finance_window

The campaign is the user's own save, so the sweep is strictly read-only with respect
to game state: it presses panel hotkeys, clicks close buttons, and nothing else.
Anything that would spend money, queue a build, or answer a decision is refused --
see SAFE_TO_PRESS. A sweep that recruited a unit to learn where the button is would
have corrupted the very campaign it was learning from.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from comstar_game_ai.game_io.campaign import modal  # noqa: E402
from comstar_game_ai.game_io.campaign import rome_shortcuts as rs  # noqa: E402
from comstar_game_ai.game_io.campaign import ui_mode  # noqa: E402
from comstar_game_ai.game_io.campaign.ui_atlas import ATLAS, PanelClass  # noqa: E402
from comstar_game_ai.game_io.input.send_input import SendInputController  # noqa: E402
from comstar_game_ai.game_io.window import find_game_window  # noqa: E402
from comstar_game_ai.shared.config import load_config  # noqa: E402

# Keys the sweep may send. Everything here either opens a panel or closes one; none
# of it commits a decision. Deliberately an allowlist: a denylist would let a new
# atlas entry introduce a state-mutating keystroke by default.
SAFE_TO_PRESS = frozenset(
    {"ctrl+1", "ctrl+2", "ctrl+3", "ctrl+4", "ctrl+5", "ctrl+6", "ctrl+7",
     "tab", "5", "6", "escape"}
)

# Keys that reach something we cannot drive. F1 is the trap: `show_help` does not
# open an in-game panel, it asks Steam to open the wiki in the overlay browser,
# which covers the whole screen, is not part of the game's UI, and only Shift+Tab
# clears it. An unattended run that pressed it would simply stop being able to see.
HAZARDOUS = {"f1": "opens the Steam overlay browser, not an in-game panel"}

# Panels that appear in answer to an event and cannot be summoned. Opening them is
# not possible; answering them would alter the campaign. Reported, never pressed.
NOT_SUMMONABLE = frozenset({PanelClass.DECISION})

SETTLE_MS = 900
DISMISS_SETTLE_MS = 700


@dataclass
class PanelProbe:
    """What one panel's visit established."""

    panel_id: str
    chord: str = ""
    status: str = "skipped"
    reason: str = ""
    screen_changed: bool = False
    change_score: float = 0.0
    bounds_px: tuple[int, int, int] | None = None
    bounds_norm: tuple[float, float, float] | None = None
    close_x_norm: tuple[float, float] | None = None
    close_x_confidence: float = 0.0
    blocking: bool = False
    covers_centre: bool = False
    ui_mode: str = ""
    capture: str = ""
    dismissed_by: str = ""
    restored: bool = False
    notes: list[str] = field(default_factory=list)


def frame_delta(before, after) -> float:
    """Mean absolute luminance difference over a coarse grid, 0..1.

    Coarse on purpose: the campaign map animates (banners, water, unit idle), so a
    per-pixel comparison never reads as unchanged even with nothing open.
    """
    import numpy as np

    a = np.asarray(before.convert("L").resize((64, 36)), dtype=np.int16)
    b = np.asarray(after.convert("L").resize((64, 36)), dtype=np.int16)
    return float(np.abs(a - b).mean() / 255.0)


def measure(image) -> dict:
    """Geometry and classification for whatever is currently on screen."""
    width, height = image.size
    bounds = modal.panel_bounds(image)
    close = modal.localize_panel_close_x(image)
    out = {
        "bounds_px": tuple(bounds) if bounds else None,
        "bounds_norm": (
            (round(bounds[0] / width, 4), round(bounds[1] / width, 4),
             round(bounds[2] / height, 4)) if bounds else None
        ),
        "close_x_norm": (round(close.x_norm, 4), round(close.y_norm, 4)) if close else None,
        "close_x_confidence": round(close.confidence, 3) if close else 0.0,
        "blocking": modal.blocking_ui_present(image),
        "covers_centre": modal.panel_covers_map_centre(image),
    }
    return out


def send_chord(pad: SendInputController, hwnd: int, chord: str) -> bool:
    """Press a chord like 'ctrl+4' or a bare key like 'f1'."""
    if "+" in chord:
        modifier, key = chord.rsplit("+", 1)
        return pad.chord_scancode(modifier, key, hwnd=hwnd)
    return pad.tap_key(chord, hwnd=hwnd)


def grab(hwnd: int):
    return ui_mode.grab_rgb_image(hwnd)


def signature(image) -> tuple[int, int, int] | None:
    """The measurable panel on screen, as (left, right, top) pixels, or None."""
    bounds = modal.panel_bounds(image)
    return tuple(bounds) if bounds else None


def at_baseline(image, baseline: tuple[int, int, int] | None, *, tol: int = 6) -> bool:
    """True when the screen is back to how the sweep found it.

    Not 'no panel at all': a real campaign usually has a notice card sitting in the
    left dock, and the sweep has no business closing the player's mission briefing.
    So the resting state is whatever was there at the start, and a panel counts as
    new only if it differs from that.
    """
    if modal.blocking_ui_present(image):
        return False
    current = signature(image)
    if current is None or baseline is None:
        return current == baseline
    return all(abs(a - b) <= tol for a, b in zip(current, baseline))


def dismiss(pad: SendInputController, hwnd: int, probe: PanelProbe, out_dir: Path,
            baseline: tuple[int, int, int] | None) -> None:
    """Return to baseline, preferring the panel's own close button.

    Escape first would be wrong: the building browser ignores it entirely, which is
    how the atlas learned that CLOSE_X has to be attempted before ESCAPE. The same
    hotkey that opened the panel is tried last, since several of these toggle.
    """
    image = grab(hwnd)
    close = modal.localize_panel_close_x(image)
    if close is not None:
        pad.click_client_norm(hwnd, close.x_norm, close.y_norm)
        time.sleep(DISMISS_SETTLE_MS / 1000.0)
        if at_baseline(grab(hwnd), baseline):
            probe.dismissed_by = "close_x"
            probe.restored = True
            return
        probe.notes.append("close_x click at %.3f,%.3f did not restore the baseline"
                           % (close.x_norm, close.y_norm))

    for attempt, chord in (("escape", "escape"), ("escape_x2", "escape"),
                           ("toggle", probe.chord)):
        send_chord(pad, hwnd, chord)
        time.sleep(DISMISS_SETTLE_MS / 1000.0)
        if at_baseline(grab(hwnd), baseline):
            probe.dismissed_by = probe.dismissed_by or attempt
            probe.restored = True
            return

    final = grab(hwnd)
    probe.restored = False
    stuck = out_dir / ("stuck_after_%s.png" % probe.panel_id)
    final.save(stuck)
    probe.notes.append("could not restore baseline; saved %s" % stuck.name)


def plan() -> list[tuple[str, str, str]]:
    """(panel_id, chord, reason_if_skipped) for every atlas entry."""
    db = rs.load_shortcuts()
    resolved = {}
    for keyset in db.keysets:
        for binding in db.bindings(keyset):
            resolved.setdefault(binding.action, binding)

    rows = []
    for panel in ATLAS:
        if panel.panel_class in NOT_SUMMONABLE:
            rows.append((panel.id, "", "decision panel: appears on an event, cannot be summoned"))
            continue
        if not panel.shortcut_action:
            rows.append((panel.id, "", "no hotkey in descr_shortcuts.txt"))
            continue
        binding = resolved.get(panel.shortcut_action)
        if binding is None or not binding.chord:
            rows.append((panel.id, "", "action %r resolves to no key" % panel.shortcut_action))
            continue
        chord = binding.chord
        if chord in HAZARDOUS:
            rows.append((panel.id, chord, "%s %s" % (chord, HAZARDOUS[chord])))
            continue
        if chord not in SAFE_TO_PRESS:
            rows.append((panel.id, chord, "%r is not on the safe-to-press allowlist" % chord))
            continue
        rows.append((panel.id, chord, ""))
    return rows


def visit(pad: SendInputController, hwnd: int, panel_id: str, chord: str,
          out_dir: Path, settle_ms: int,
          baseline_sig: tuple[int, int, int] | None) -> PanelProbe:
    probe = PanelProbe(panel_id=panel_id, chord=chord)

    baseline = grab(hwnd)
    if not at_baseline(baseline, baseline_sig):
        stray = out_dir / ("baseline_drift_%s.png" % panel_id)
        baseline.save(stray)
        probe.status = "aborted"
        probe.reason = "screen drifted from the baseline before pressing; saved %s" % stray.name
        return probe

    send_chord(pad, hwnd, chord)
    time.sleep(settle_ms / 1000.0)
    after = grab(hwnd)

    probe.change_score = round(frame_delta(baseline, after), 4)
    # 0.01 clears map animation (water, banners) while catching a panel, which moves
    # a large fraction of the frame.
    probe.screen_changed = probe.change_score > 0.01

    for key, value in measure(after).items():
        setattr(probe, key, value)
    probe.ui_mode = ui_mode.classify_campaign_image(after).mode.value

    shot = out_dir / ("%s.png" % panel_id)
    after.save(shot)
    probe.capture = shot.name

    if not probe.screen_changed:
        probe.status = "no_response"
        probe.reason = "the hotkey moved nothing on screen"
        return probe
    if probe.bounds_px is None:
        probe.status = "changed_without_panel"
        probe.reason = "screen changed but no cream panel was measurable"
    elif probe.bounds_px == baseline_sig:
        probe.status = "baseline_panel_only"
        probe.reason = "the only panel measurable is the one that was already there"
    else:
        probe.status = "measured"

    dismiss(pad, hwnd, probe, out_dir, baseline_sig)
    return probe


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", action="append", default=[], metavar="PANEL_ID")
    ap.add_argument("--out", default=str(Path("data") / "runtime" / "sweep"))
    ap.add_argument("--settle-ms", type=int, default=SETTLE_MS)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    rows = plan()
    if args.only:
        rows = [r for r in rows if r[0] in set(args.only)]
        if not rows:
            print("no atlas panel matches %s" % args.only, file=sys.stderr)
            return 2

    actionable = [r for r in rows if not r[2]]
    print("sweep plan: %d panels, %d actionable\n" % (len(rows), len(actionable)))
    for panel_id, chord, skip in rows:
        print("  %-26s %-8s %s" % (panel_id, chord or "-", skip or "-> press"))
    if args.dry_run:
        print("\ndry run -- nothing pressed")
        return 0
    if not actionable:
        print("\nnothing actionable")
        return 0

    cfg = load_config()
    game = find_game_window(cfg.get("game", {}).get("window_title_substrings", ["Rome"]))
    if game is None:
        print("\nFAIL Rome window not found", file=sys.stderr)
        return 1

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    pad = SendInputController()
    if not pad.focus_window(game.hwnd):
        print("\nFAIL could not focus the game window", file=sys.stderr)
        return 1
    pad.normalize_keyboard_state()
    time.sleep(0.4)

    opening = grab(game.hwnd)
    classified = ui_mode.classify_campaign_image(opening)
    if modal.blocking_ui_present(opening):
        shot = out_dir / "precondition_failed.png"
        opening.save(shot)
        print("\nFAIL something blocking is on screen -- saved %s" % shot, file=sys.stderr)
        return 1

    baseline_sig = signature(opening)
    opening.save(out_dir / "baseline.png")
    print("\nbaseline: mode=%s panel=%s" % (
        classified.mode.value,
        "none" if baseline_sig is None else "l=%d r=%d t=%d" % baseline_sig))
    if baseline_sig is not None:
        print("          a notice is already open; it is left alone and treated as the"
              " resting state")

    print("\n%-26s %-8s %-22s %-8s %s" % ("panel", "chord", "result", "delta", "geometry"))
    probes = []
    for panel_id, chord, skip in rows:
        if skip:
            probes.append(PanelProbe(panel_id=panel_id, chord=chord,
                                     status="skipped", reason=skip))
            continue
        probe = visit(pad, game.hwnd, panel_id, chord, out_dir, args.settle_ms, baseline_sig)
        probes.append(probe)
        geom = ("l=%.3f r=%.3f t=%.3f" % probe.bounds_norm) if probe.bounds_norm else "-"
        close = (" x@%.3f,%.3f" % probe.close_x_norm) if probe.close_x_norm else ""
        print("%-26s %-8s %-22s %-8.4f %s%s" % (
            panel_id, chord, probe.status, probe.change_score, geom, close))
        if probe.notes:
            for note in probe.notes:
                print("%-26s %s" % ("", note))
        if probe.status == "aborted":
            print("\nstopping: the screen is not in a known state", file=sys.stderr)
            break

    report = out_dir / "sweep_report.json"
    report.write_text(json.dumps([asdict(p) for p in probes], indent=1), encoding="utf-8")

    measured = [p for p in probes if p.status == "measured"]
    restored = [p for p in measured if p.restored]
    print("\n%d measured, %d restored the map cleanly, %d skipped" % (
        len(measured), len(restored), sum(1 for p in probes if p.status == "skipped")))
    print("wrote %s" % report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
