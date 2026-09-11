# Map→window projection for campaign marches

How belief coordinates on the Rome map become mouse clicks in the Remastered window — and why that path exists.

## Why this exists

The campaign director (AO) thinks in **map space**:

| Who / what | Belief map XY |
|---|---|
| Flavius Julius | `(89, 82)` |
| Segesta | `(83, 84)` |

The game only accepts input in **client-normalised window coordinates** `(0..1, 0..1)` relative to the Rome client rect. A click at map `(83, 84)` is meaningless until the **current camera pose** turns it into something like `(0.31, 0.42)`.

Older code assumed Lists-locate had put the army at screen centre and **left-clicked** along a fixed bearing. That failed when:

1. the wrong Lists row was selected (Amulius instead of Flavius),
2. the camera was elsewhere,
3. a left-click hit a nameplate and **selected the town** instead of ordering a march.

Remastered issues move / attack / besiege on a **right-click** once the cursor glyph changes (boots / sword).

```mermaid
flowchart TD
  order[March order: actor + Segesta map xy]
  select[Select and verify ordered army]
  calib[Calibrate map to client for this pose]
  project[Project destination map xy to client xy]
  hover[Hover; require cursor glyph]
  click[Right-click destination]
  order --> select --> calib --> project --> hover --> click
```

---

## Two coordinate spaces

![Map space vs client norms for Flavius → Segesta](assets/map-projection/coord-spaces-flavius-segesta.png)

### Map space (belief)

- Comes from start-position / `list_characters` style data stored in the belief store.
- **X increases east**, **Y increases north** (Rome convention).
- Independent of zoom, pan, or which monitor the window sits on.

### Client norms (window)

- `(0, 0)` = top-left of the **client area** (not the monitor).
- **X increases right**, **Y increases down**.
- Converted to screen pixels via `ClientToScreen` before `SendInput`.

Safe click region (must stay out of HUD / radar):

```text
DEFAULT_VIEWPORT_BOUNDS = (0.08, 0.10, 0.82, 0.58)
# left, top, right, bottom — bottom capped above the army parchment
```

---

## End-to-end pipeline

![Near-path march pipeline](assets/map-projection/march-pipeline-near.png)

| Step | What happens | Failure = refuse |
|---|---|---|
| 1. Select | Lists → Military Forces → row → locate | No unit cards |
| 2. Verify | Radar frustum centre ≈ ordered `from_xy` | Wrong army (e.g. Amulius) |
| 3. Calibrate | Build a `MapClientTransform` for **this** pose | Cannot fit / no fallback |
| 4. Project | Map destination → client XY (with blends) | Outside safe viewport |
| 5. Glyph | Hover until cursor handle ≠ baseline | Open land / HUD / water |
| 6. Actuate | **Right-click** | No controller / no screen coords |

Primary code:

- [`map_projection.py`](../../src/comstar_game_ai/game_io/campaign/map_projection.py) — math + radar helpers  
- [`march.py`](../../src/comstar_game_ai/game_io/campaign/march.py) — gates + click path  
- Config: `campaign.march.use_map_projection: true` (legacy bearing probes off by default)

---

## Calibration modes (how map becomes client)

Ideal path (plan Phase 0): hover known client points → `show_cursorstat` → affine fit.  
**Live Remastered spike:** `show_cursorstat` is console-pane-only — nothing useful lands in `message_log` / `scripting_log`. So we do **not** ship assumed-centre geometry as the “better” path; we use these fallbacks:

### A. Army-anchor (near marches — primary today)

After Lists-locate, Rome frames the ordered stack near screen centre. We treat:

```text
army map xy  →  client (0.50, 0.48)
```

and apply a north-up similarity:

```text
x_client = 0.50 + scale * (x_map - x_army)
y_client = 0.48 + scale * (-1) * (y_map - y_army)
```

`DEFAULT_ANCHOR_SCALE` = **client-norms per map unit** at typical post-locate zoom.

| Scale | Meaning |
|---|---|
| `0.032` (current) | Tuned after live overshoot into the gulf west of Segesta |
| `0.041` (old) | Too large — destination projected past the town into water |

**Worked example — Flavius → Segesta**

```text
army   = (89, 82)
dest   = (83, 84)
Δ      = (-6, +2)          # 6 west, 2 north
scale  = 0.032

x = 0.50 + 0.032 * (-6) = 0.308
y = 0.48 + 0.032 * (-1) * (+2) = 0.416

→ project ≈ (0.31, 0.42)
```

That lands **west of Flavius, above the army HUD** — the same side of the screen as Segesta.

### B. Dest-anchor (after radar frame)

For **far** targets (`map distance > 20`), we radar-click the destination belief point so it should appear near centre, then use the same formula with `army_map_xy = destination`.

### C. Frustum AABB (weak)

Detect the red radar trapezoid → axis-aligned map AABB → linear map to the viewport. Useful as a **selection check** (“is the framed army near `from_xy`?”). Too coarse alone for settlement clicks: live run projected Segesta to `(0.443, 0.700)` into empty grass / parchment. Frustum is **rejected** unless the projected point lands near screen centre after a radar frame.

### D. Full affine from `show_cursorstat` (preferred when readable)

≥3 samples → least-squares 2×3 affine. Kept in the module; unused until the console log path works.

---

## Near vs far

| | Near (`dist ≤ 20`) | Far |
|---|---|---|
| Example | Flavius→Segesta (~6.3) | Cross-Italy march |
| After select | **Stay** on army-locate pose | Radar-jump toward destination |
| Calibrate | `army_anchor` | `dest_anchor` (frustum only if near centre) |
| Why | Radar jump was the “minimap click” operators noticed; frustum then aimed into the HUD | Destination not on screen after locate |

---

## Projection blends (undershoot first)

Belief scale is approximate. A single full-offset click overshot Segesta into water:

![Live miss: cursor in water west of Segesta](assets/map-projection/live-overshoot-water-west-of-segesta.jpg)

*Operator photo, 2026-09-11. Yellow cursor in the gulf; Segesta is the settlement immediately to the right (east) of the click.*

So for near targets we walk **along the army→destination segment** in map space, then project each point:

```text
NEAR_PROJECTION_BLENDS = (0.75, 0.85, 0.95, 1.0, 1.08)
```

![Blend probes for Flavius → Segesta](assets/map-projection/blend-probes-segesta.png)

| Blend | Map point (approx) | Client (scale 0.032) | Intent |
|---|---|---|---|
| 0.75 | (84.5, 83.5) | ~(0.36, 0.43) | Undershoot — toward town from army |
| 0.85 | (84.1, 83.7) | ~(0.34, 0.43) | |
| 0.95 | (83.3, 83.9) | ~(0.32, 0.42) | |
| 1.00 | (83.0, 84.0) | ~(0.31, 0.42) | Full belief offset |
| 1.08 | (82.5, 84.2) | ~(0.29, 0.41) | Slight overshoot last |

At each probe: hover → read `HCURSOR` → if it changed vs neutral baseline → **right-click** and stop.  
No glyph on any probe → refuse (`no_move_cursor`). Never left-click the destination.

---

## Selection gate (don’t march Amulius)

Config still lists a preferred Military Forces row `(0.30, 0.415)`, which has been Amulius. Projection does **not** trust that row alone.

After each locate:

1. Grab frame, detect radar frustum AABB in map space.
2. If frustum **centre** is far from ordered `from_xy` (> ~22 map units) → try next row.
3. If frustum unavailable → tentative cards-only; glyph gate still refuses a wrong pose.

Destination projection finds **where** to click; selection still decides **who** receives the order.

---

## Vision / labels (optional, not primary)

With `use_map_vision: true`, Ada may confirm a nameplate after projection. It must not be the only locator:

- Labels can be off (`LABEL_SETTLEMENTS:FALSE`).
- Prose answers like `red SEGESTA nameplate left of selected army` are unparseable without JSON mode.

Vision success → hover that point → glyph → right-click.  
Vision miss → continue with projection probes.

---

## Logging (what to look for)

Successful near march should look like:

```text
MARCH select: row (...) verified via frustum who=Flavius Julius cards=…
MARCH calib: army_anchor scale=0.032 at map=(89.0,82.0)
MARCH project: map=(83.0,84.0) → client=(0.308,0.416) calib=army_anchor probes=5 …
MARCH project: glyph at (0.336,0.426) …
MARCH ordered click=(…) button=right … calib=army_anchor who=Flavius Julius
```

Debug frames (runtime only): `data/runtime/map_projection_debug/` with the projected point drawn.

Bad signs from earlier runs:

| Log | Meaning |
|---|---|
| `calib=frustum` → `(0.44, 0.70)` | HUD / grass miss |
| `MARCH frame: radar click (0.928,…)` on a near target | Unnecessary minimap jump |
| `button` missing / left path | Should be right-click |
| `malformed_json` on AO | Unrelated: director answer sanitised — fixed via `responseFormat` on `ao_reach` |

---

## Config knobs

```yaml
campaign:
  march:
    use_map_projection: true      # primary path
    allow_legacy_geometry: false  # old assumed-centre probes
    use_map_vision: true          # optional Ada confirm
```

Code knobs on `MarchDirector`:

| Field | Default | Role |
|---|---|---|
| `anchor_scale` | `0.032` | Client norms per map unit |
| `use_map_projection` | `true` | Master switch |
| `allow_legacy_geometry` | `false` | Last-resort bearing probes |
| `debug_frame_dir` | runtime folder | Annotated miss/hit JPEGs |

---

## Acceptance checklist

- [ ] Wrong preferred Lists row does not keep Amulius when Flavius `from_xy` is ordered.
- [ ] Camera parked with Home still finds a near Segesta after locate (no reliance on prior framing).
- [ ] Projected click is on the **campaign map**, not the radar widget.
- [ ] Destination actuation is **right-click**; glyph required.
- [ ] Near miss into water is recovered by undershoot blends or a lower `anchor_scale`.
- [ ] Annotated debug frame saved on order / refuse.

Live helpers:

```powershell
python scripts/accept_map_projection_march.py --park-home
python scripts/run_phase2_actuation.py --directives --seconds 12
```

---

## Out of scope (by design)

- Perfect 3D / heightmap projection — affine-per-pose is enough for strat clicks.
- Cheats (`toggle_fow`, etc.).
- Replacing AO blocking / sequencing.

---

## File map

| Path | Role |
|---|---|
| `src/.../map_projection.py` | Affine, army/dest anchor, radar↔map, frustum CV |
| `src/.../march.py` | Select / frame / project / glyph / right-click |
| `src/.../input/send_input.py` | `right_click` / `right_click_client_norm` |
| `scripts/accept_map_projection_march.py` | Live Flavius→Segesta acceptance |
| `scripts/spike_show_cursorstat.py` | Phase 0 spike (unreadable on Remastered) |
| `docs/design/assets/map-projection/` | Diagrams + operator photo used above |
