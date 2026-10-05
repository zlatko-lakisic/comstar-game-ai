# Cursorstat gate capture — Claude handoff

**Date:** 2026-10-04
**Repo:** `comstar-game-ai`
**Branch:** `feat/map-homography` (uncommitted; do not commit unless asked)
**Status:** The self-driving capture succeeded. The locked read gate is **not** opened. Frames are unlabeled.

---

## 1. What finished

`scripts/capture_cursorstat_gate.py` drove the Julii campaign map with WASD, read `show_cursorstat` at the cross center after every pan, and saved a 44-point sample at each target.

Successful session (gitignored):

`data/runtime/cursorstat_sessions/20261003-gate17`

| | |
|---|---|
| Exit | 0 |
| Frames | 220 (5 × 44) |
| Labels | all `xy: null`, `label_source: unlabeled` |
| Missed | `[]` |

Centers the seek accepted (Chebyshev ≤ 3). These reads steered the camera. They are **not** ground truth.

| Target | Center read |
|---|---|
| 44, 44 | 44, 45 |
| 84, 84 | 84, 81 |
| 100, 100 | 100, 101 |
| 141, 141 | 142, 142 |
| 200, 55 | 200, 55 |

Command that produced it (game already focused, no Enter wait):

```powershell
python scripts/capture_cursorstat_gate.py --session 20261003-gate17 --countdown 2 --now
```

Sessions `20261003-gate` through `20261003-gate16` are failed attempts. Do not label them. Do not reuse a session directory; the script refuses an existing one.

---

## 2. What the capture does

| Piece | Path |
|---|---|
| Live capture | `scripts/capture_cursorstat_gate.py` |
| Seek decisions | `src/comstar_game_ai/game_io/campaign/camera_seek.py` |
| Seek tests | `tests/unit/test_camera_seek.py` (13 passed) |
| Lock (not run) | `scripts/lock_cursorstat_gate.py` writes `split_v2.json` only when labels are complete |
| Score once (not run) | `scripts/score_cursorstat_gate.py` writes `gate_report_v2.json` |

Keys, measured on this campaign: **D east, A west, W north, S south.** Map Y increases north. Not arrow keys.

The 44-point cross is horizontal `y=0.45`, `x=0.30..0.70` step `0.018` (23 points) plus vertical `x=0.50`, `y=0.26..0.62` step `0.018` (21 points). The seek probes client `(0.50, 0.45)`.

Targets: `(44, 44)`, `(84, 84)`, `(100, 100)`, `(141, 141)`, `(200, 55)`. Those cover adjacent numbers 44 / 84 / 100 / 141, hundreds digit 0 (`x=44`), 1 (`100` and `y=100` / `141`), and 2 (`x=200`). Hundreds digits 3–9 cannot occur (map max x 254, y 155).

Close enough is Chebyshev ≤ 3 (`CLOSE_MAP_UNITS`). Hold is `error / measured rate`, clamped to 0.08–0.60 s. An unmeasured key uses the known sign at a 0.20 s probe. `estimate_after` uses the measured rate, or 45 map units/second along the known sign when the console cannot be read (open sea near Cilicia). A read whose jump exceeds `hold * 70 + 4` is replaced by that estimate. Do **not** pan again from the old coordinate: that loop held A and drove the camera to the Atlantic edge.

Once one axis is already within 3, only the other axis is moved. Otherwise a 4-unit Y error at ~45 units/s outscores a 26-unit X error and the seek bobs north/south forever (`70, 42` vs target `44, 44`).

---

## 3. Console toggle

Backtick (`` ` ``, VK `0xC0`) toggles the console. `RomeShell.console_open` desyncs from the game. The capture sets the flag from the picture before open/close.

`_console_is_open` is **not** a brightness cutoff. Measured:

| Picture | Top band (y 100–135) | Map below (y 170–210) |
|---|---|---|
| Open over Cilicia | ~23 | ~64 (delta ~41) |
| Closed over Cilicia | ~77 | ~72 (delta ~−6) |
| Open over dark forest | ~8 | — |
| Closed dark forest | ~26 | — |

Open if the top band is `< 12`, or more than 18 levels darker than the map below it. A cutoff of 30 treated dark forest as open and skipped the backtick. A cutoff of 20 treated an open console over Cilicia as closed, so D was typed into the console (`dshow_cursorstat`) and the camera looked stuck at x=185. One real D 0.30 s from there moved `(185, 54)` → `(199, 55)`.

WASD is sent only after the console is closed. `show_cursorstat` is sent only after it is open. **Do not press Escape.** Escape opens the pause menu (Return to Game / Help Sheet). Recovery is one Escape only when the center of the frame is parchment (mean gray ≥ 140).

The north map border (patterned wall, Britannia) has no tile under the cross. `show_cursorstat` then prints `err: failed to retrieve cursor interaction point`. Hold S until land is under `(0.50, 0.45)`. The east scroll is not clamped at 185; that stop was the console eating D.

---

## 4. Reader changes in this session

File: `src/comstar_game_ai/game_io/campaign/console_cursorstat.py`
Tests: `tests/unit/test_console_cursorstat.py` (18 passed).

Confidence is still the worst **kept** glyph agreement. It is not a completeness score. A dropped digit used to leave a short number at 0.78 or 1.0. Refusals return `confidence=None`.

Behavior added, in the order a live frame hits it:

1. **Line finder.** Ink ≥ 60 in x=60–140, y=80–150. A row counts at ≥ 8 pixels (was 11). A live pos line’s second row had 9. If no exact 6 px run exists, a 6-row window is kept when 5 rows meet 8 and every row has ≥ 4. That is how `pos 47,78` was found. Train frames still have their exact 6 px run, so this window is not used on them.
2. **Out of map.** Refuse outside `x` 0–254 and `y` 0–155. `map_regions.tga` is 255×156. Do not use the radar box `(0, 0, 200, 150)`.
3. **Comma split.** `109,80` has the comma one column from the 8 (gap of 2). Split the number when a bottom-only column sits in the gap, not only when the gap is wider than 2.
4. **Unexplained ink.** The coordinate span grows one blank column backward and **three** forward (the docstring in `_unexplained_columns` still says two; the code stops after `blanks > 3`). A leftover glyph refuses the short number. This is what turned a truncated `81` into a real `(70, 81)` instead of an accepted `(70, 8)`.
5. **Faint retry.** If the strict grid (ink 60) refuses unexplained ink, the same 6 px line is rebuilt from ink 59 down to 46. Keep the complete read with the **most digits**. A higher cutoff can drop a leading digit and still look finished (`142` → `2`). A line that already reads at 60 is not rebuilt. `zoom0/grid_09.png` still refuses `10, 90`. `settlement_segesta.png` still refuses `83, 8`.
6. **One orphan column.** A live `0` can score lower than the `1` made from its right two columns, leaving the left column unexplained (`43, 151` painted as a noisy 0, read as `43, 150`). If exactly one leftover column is covered by a wider glyph above the 0.60 floor, that wider glyph replaces the narrow one. A dropped digit with no covering glyph stays refused.

Do not lower the global ink threshold to 50. That reads some live frames and destroys the 6 px run on saved train frames.

---

## 5. What not to do next

- Do not treat reader output as the labels for `20261003-gate17`. Glyph labels come from the pictures, then `lock_cursorstat_gate.py --test 20261003-gate17`, then `score_cursorstat_gate.py` **once**. The gate is zero wrong reads. Misses are allowed.
- Do not rescore `split.json` / `gate_report.json` / `20261003-heldout`.
- Do not cut templates from `20261003-heldout`. Train sessions that must not be the test set: `20261003-pass`, `20261003-digits3`.
- Do not publish `data/runtime/homography_sessions/fit_report.json`. Do not overwrite `zoom0` / `zoom1` / `zoom2` or refit their reports. The live homography gate failed earlier because truncated reads poisoned it. Held-out limit stays 3 map units. Nothing was published.
- Do not change the director pin. Do not apply stash `ada-model-local`.
- Parked, still parked: settlement YOLO, army/ship labels, Z4, Z6, far-path Segesta, hostile pose, retraining.
- March still does not call this reader. A valid fit would still not click (`ambiguous`) until move/sword cursor handles are set.

Offline check:

```powershell
python -m pytest tests/unit/test_console_cursorstat.py tests/unit/test_camera_seek.py
```
