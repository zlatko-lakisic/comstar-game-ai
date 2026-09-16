# Canonical zoom, surface detection, and the fitted-expectation defect

**For an AI coding agent working in the `comstar-game-ai` repo.**

This amends the camera-pose **P** series (documented in
`docs/design/map-window-projection.md` § Canonical camera pose). There is no
separate in-repo `camera-pose-reset-handoff.md`; treat that design section as the
P-series home. **P2, P4, P7 and P8 stand. P1, P3, P5 and P6 are corrected here.**

Written in response to [`docs/map-overlay-zoom-handoff.md`](map-overlay-zoom-handoff.md),
the live investigation of 2026-09-11 in which four consecutive attempts on turn 6
produced zero marches in four and a half minutes.

Changes are prefixed `Z`.

Written 2026-09-11.

**Operator decisions (2026-09-11):**

| # | Decision |
|---|----------|
| Margin | Do not pick a default before measuring; choose against the known H−Q gap after the Z2 sweep |
| Circuit breaker | Escalate via overlay fault (`verification` ok=false), then **end the run** — not hold-and-advance |
| Survey pose | Skip entirely — no consumer; belief is telemetry / `descr_strat` |
| Phase stop | After Z2 sweep report H, Q, window size, dual-surface Z3 stats — do not lock `zoom_steps_from_max_in` or run Z7 |

---

## 0. Rules of engagement

1. **Never fit an expected value to a pose that has not produced a working order.** This is the central rule of this document and the reason the previous failure was invisible. Section 1.2 explains it.
2. **Treat `expected_aabb_width_map: 80.8` and `DEFAULT_ANCHOR_SCALE: 0.0092` as void.** Both were fitted at the broken pose. Do not carry them forward, do not tune from them, do not use them as a starting point. They are measurements of a state that should never occur.
3. **Do not anchor the canonical pose to a boundary that has a UI mode on it.** Section 2, Z1.
4. **Do not weaken the glyph gate.** It was the only layer that caught this. See section 5.
5. **Do not touch the projection blend ladder, glyph templates, AO timeouts, or hold-floor policy.** The only projection value this document changes is the scale tied to the new pose.
6. **Stop and ask** on anything in section 7 (operator answers above supersede open questions where marked).

---

## 1. What went wrong

### 1.1 The chain

The canonical pose specified maximum zoom-out, implemented as roughly 42 presses of `zoom_out` to guarantee saturation against the engine clamp.

On Rome Remastered, continuing to zoom out past a threshold shows a banner reading that further scrolling will toggle the Map Overlay, and then opens it. The Map Overlay is the political and factions colour view. It replaces the 3D map. Orders are not valid on it.

The march then projected correctly, hovered five points, found no move glyph on any of them, and refused. The three attempts that followed were fallout: a quiesce timeout against a still-animating or wrong surface, then a UI sync loop misreading the army parchment as a dismissable notice, then four failed Lists selections and `stack_not_selected`.

### 1.2 The defect that matters

The pose verification **passed**, reporting `aabb_w=82.1` against an expected `80.8`.

It passed because the Map Overlay keeps the radar, so the frustum still exists and its extent is still measurable. The AABB measures how far out the camera is. It carries no information about which surface is being rendered. The check confirmed the one property it measures and was structurally incapable of reporting the property that had broken.

**And `expected_aabb_width_map: 80.8` was itself measured at that same zoom.** So the verification was calibrated against the broken state and would certify it every time. A reference fitted to an unvalidated pose does not validate that pose, it ratifies it.

This is the more serious of the two defects. The wrong zoom value is a number. The verification that cannot see the failure is a design flaw, and it would have hidden any other surface problem just as effectively.

The same applies to `DEFAULT_ANCHOR_SCALE: 0.0092`, which was derived as `0.74 / 80.8` from the same bad frame.

---

## 2. The changes

### Z1. Invert the saturation: clamp on zoom in, step out

The saturation principle was chosen because a hard clamp erases the camera's history, so the result does not depend on the starting state. That reasoning still holds. It was applied to the wrong edge.

The zoom-out extreme is not a clamp. It is a soft UI trigger with a mode change sitting on it, and a soft trigger can move with resolution, window size, aspect ratio or a patch. Anchoring to it, or to a fixed offset from it, means the canonical pose drifts back into the overlay whenever that threshold moves.

**Saturate on `zoom_in` instead, then step out a fixed count.**

```
reset_zoom():
    press zoom_in  × zoom_in_saturate_presses     # to the hard clamp
    press zoom_out × zoom_steps_from_max_in       # to the canonical pose
```

`zoom_in_saturate_presses` should cover the full range with margin. The measured range was about 34 presses, so 40 is a reasonable starting figure, matching the existing zoom-out value.

**Verify the in-clamp is actually a clamp before trusting it.** Do not repeat the previous error by assuming a boundary is clean because it is a boundary. Drive to maximum zoom in, run the surface check from Z3, and confirm the 3D map is still rendered and no mode has changed. If maximum zoom in also changes surface or enters a different camera mode, report that and stop, because then neither extreme is a safe reference and the approach needs rethinking rather than adjusting.

### Z2. Choose the canonical zoom by margin, between two bounds

The canonical zoom is no longer defined as an extreme. It sits between two measured limits, and both go in the design doc.

**Upper bound, the hazard.** Zoom out from the in-clamp one press at a time, running the Z3 surface check after each, and record the press count at which the toggle banner first appears / Z3 reports overlay. Call it `H`.

**Lower bound, the quantization floor.** This was specified in the original zoom decision and never applied. Zoom in far enough and reach suffers, so this is a floor rather than a target. At the canonical pose, a settlement must remain a comfortably clickable target, around 15 to 20 px on screen. Record the press count at which that floor is met. Call it `Q`.

**Canonical sits inside both, with margin from `H`.** The margin exists because `H` may move between machines and patches. **Do not pick the margin before the sweep** — choose against the measured H−Q gap (operator).

Record `H`, `Q`, and the chosen value in `docs/design/map-window-projection.md`, with the window size they were measured at, because both bounds are resolution dependent.

### Z3. Detect the surface by image statistics, not by the banner

The investigation recommends OCR or template matching on the toggle string. Do not do that as the primary check, for two reasons.

**The banner is transient.** It appears during the scroll and is gone once the overlay is open. A check that runs after the transition completes sees no banner and a fully broken state. There is a timing window in which banner detection returns clean while the surface is wrong.

**It chases the announcement rather than the state.** Template or OCR matching also binds you to locale and to a UI string that can change.

**Check the surface itself.** The overlay replaces textured terrain with flat political colour. The discriminators are cheap and robust:

- **Local variance** collapses. Terrain has texture, coastline detail and shadow gradient. Flat faction fills do not.
- **Saturation** rises and concentrates into a small number of distinct hues.
- **Edge density** falls, apart from hard region boundaries.

Sample a fixed rectangle inside the map area, well clear of the HUD, the radar and the army parchment, since those render identically on both surfaces and would dilute the signal. Calibrate the thresholds by capturing both surfaces once during the Z2 sweep, and record the measured values.

This check is **separate from the pose check and runs before projection.** It answers a different question and must not be folded into the AABB comparison, which is what created the blind spot in the first place.

### Z4. Add `map_overlay` as a distinct `local_mode`

*(Deferred past the Z2 sweep stop in phase 1.)*

The classifier reported `campaign_map` at confidence 0.70 while the overlay was open.

A classifier whose label set excludes a real state will always return the nearest wrong answer, and it will attach a confidence that looks usable. That is worse than a low-confidence answer, because a low confidence would have triggered another look.

Add `map_overlay` to the label set. The Z3 statistics can drive it directly, so this is a label and a threshold, not a new model.

This does not make the classifier the surface guard. Z3 remains the gate. But leaving a known state out of the label set guarantees that the next surface problem presents exactly like this one.

### Z5. Add refusal code `wrong_surface:map_overlay`

*(Deferred past the Z2 sweep stop in phase 1.)*

Distinct from `pose_unverified` and from `no_move_cursor`, because all three mean different things and have different recoveries.

| Code | Meaning | Recovery |
|---|---|---|
| `pose_unverified` | The camera is not in the canonical pose | Retry the reset, then refuse |
| `wrong_surface:map_overlay` | The pose may be fine but the wrong surface is rendered | Z6 |
| `no_move_cursor` | Right surface, right pose, nothing orderable at any probe | Refuse. This is the correct last line and stays |

Log the Z3 statistics with the refusal, so a threshold that is drifting is visible in the log rather than inferred from a pattern of failures.

### Z6. Bounded recovery from the overlay

*(Deferred past the Z2 sweep stop in phase 1.)*

If Z3 reports the overlay:

1. Press `zoom_in` a bounded increment.
2. Quiesce, per P4.
3. Re-run the Z3 check.
4. Repeat until the surface check passes or an attempt cap is reached.
5. Cap reached means `wrong_surface:map_overlay`, not one more press.

Do not use Tab or the eye disc to toggle out. The overlay was entered by scroll, and leaving by a different mechanism risks a state where the scroll toggle is still armed. Reverse the action that caused it.

The cap matters for the same reason it mattered in P3. A window that is ignoring input would otherwise produce an unbounded press loop.

### Z7. Re-derive the expectations, but only after a march succeeds

*(Deferred — do not run until after margin / steps are locked and a march lands.)*

This is the rule from section 0 applied concretely, and the order is not negotiable.

1. Set the canonical pose per Z1 and Z2.
2. Confirm Z3 reports the 3D map at that pose.
3. **Run a march and land it.** Use the Flavius to Segesta near case. The glyph gate must produce a sword or boots and the order must execute.
4. **Only then** measure `expected_aabb_width_map` at that pose.
5. **Only then** derive `anchor_scale` as `viewport_width_client / aabb_w`.
6. Record both, with the window size, the press counts, and the date, in `docs/design/map-window-projection.md`.

Step 3 before steps 4 and 5 is the whole point. A number fitted to a pose that has never produced a working order is a number that will certify a broken pose.

If the march in step 3 cannot be landed at the chosen zoom, the zoom is wrong and you go back to Z2. Do not proceed to fit numbers to it and then debug the march afterwards.

### Z8. Circuit breaker on repeated identical failure

Four attempts, one turn, the same refusal, roughly 45 seconds of director time each because the hold floor reasks. The loop spent four and a half minutes confirming something the first attempt had already established.

If attempt `N` fails with the same refusal code, on the same turn, with the same `state_hash` as attempt `N-1`, stop the loop. Do not issue another AO call.

**Escalate to the operator** via the existing overlay fault path (`EventKind.VERIFICATION` with `ok: false` → `SurfaceState.FAULT`), then **end the run**. Explicitly not hold-and-advance: that recreates always-hold by another route.

Log the stop with all three matching values so the reason is legible.

### Z9. Disable `map_target_vision` until the response format is fixed

It consumed 25.4 seconds in attempt 1 and returned prose that could not be parsed, which is the same failure shape already recorded in the projection design doc.

That is roughly a third of the attempt wall clock for no value. Vision is documented as optional and never the primary locator, so turning it off costs nothing today.

Set `use_map_vision: false` and leave a note pointing at the response format work. Turn it back on when it returns structured output, not before.

---

## 3. Order of work

```
Z9  disable vision                                    independent — do first
Z8  circuit breaker                                   independent — do first
Z1  invert saturation, verify the in-clamp is clean   blocks everything else live
Z3  surface check                                     needed by Z2's sweep
Z2  measure H and Q, choose canonical                 needs Z1 and Z3; STOP after report
Z5  refusal code                                      after sweep
Z6  bounded recovery                                  after sweep
Z4  classifier label                                  after sweep
Z7  re-derive expectations                            last, and only after a march lands
```

Phase 1 stops after the Z2 sweep report.

---

## 4. Acceptance (full series)

1. **The in-clamp is verified clean.** Maximum zoom in reports the 3D map under Z3, with the measured statistics recorded.
2. **Both bounds are recorded.** `H` and `Q` appear in the design doc with the window size they were measured at, and the canonical value sits between them with the agreed margin.
3. **No banner, no overlay.** Across 20 consecutive pose resets from arbitrary starting cameras, no captured frame shows the toggle banner or overlay legends, and Z3 passes every time.
4. **The surface check catches a deliberate break.** Manually open the Map Overlay, then run a march. It refuses with `wrong_surface:map_overlay`, not with `no_move_cursor` and not with a passing pose check.
5. **Recovery works and is bounded.** From a manually opened overlay, the agent zooms back in, passes Z3, and proceeds. With input blocked, it refuses at the cap rather than pressing indefinitely.
6. **A march lands before any number is written down.** The Flavius to Segesta acceptance script is green at the new pose, and the commit that records `expected_aabb_width_map` and `anchor_scale` comes after the commit that proves the march.
7. **The old values are gone.** `grep` for `80.8` and `0.0092` returns nothing outside historical notes in the design doc explaining why they were void.
8. **The circuit breaker fires.** Force a repeatable refusal and confirm the loop stops after the second identical failure rather than continuing to 20.

Phase 1 subset: handoff + Z9 + Z8 + Z1/Z3 + Z2 report (items 1 partial, 8, void active constants).

---

## 5. What worked, and must not be weakened

The glyph gate was the only layer that caught this.

The pose check passed. The classifier passed with a usable-looking confidence. Vision failed without saying so. The glyph gate hovered five points, found nothing orderable, and refused.

The system failed safe. It did not order an army around a political map and report success. That is the closed loop doing exactly what it exists for, and it is the reason this incident cost four minutes rather than a corrupted campaign.

The investigation's recommendation that a glyph miss alone is not sufficient is correct as an argument for adding the surface check **before** it. It is not an argument for relaxing the gate. Keep it exactly as strict as it is.

---

## 6. Documentation that must change

| Document | Change |
|---|---|
| `docs/design/map-window-projection.md` | Canonical camera pose section. Replace max-out with the Z1 and Z2 scheme, record `H`, `Q`, the margin, the window size, and the new fitted values with their date |
| Same, new subsection | Record why `80.8` and `0.0092` were void, so nobody recovers them from git history believing they were merely stale |
| `docs/cursor-handoff.md` section 3 | Add two silent failures: a verification fitted to an unvalidated reference, and a classifier returning a confident label for a state absent from its label set |
| Camera pose P-series home | Note that P1, P3, P5 and P6 are amended by this document |

The first entry in the section 3 addition is the generalisable one. It is not specific to cameras. Any expected value derived from an observation of a state you have not independently validated will certify that state, and the project now has one worked example of it costing a day.

---

## 7. Ask, do not decide

| # | Question | Status |
|---|---|---|
| 1 | **The margin between canonical zoom and `H`.** | Open until Z2 sweep reports the H−Q gap |
| 2 | **Whether to keep a separate zoomed-out survey pose** | **Closed: no.** Skip entirely |
| 3 | **What the circuit breaker does when it fires** | **Closed:** escalate (overlay FAULT) then end the run — not hold-and-advance |
| 4 | **Whether `Q` is even binding** | Resolves from the same Z2 sweep; report with H |

---

## 8. Not in scope

- The projection blend ladder, the glyph templates, or the hover mechanism
- AO timeouts and the hold-floor policy, both of which behaved correctly
- The sword-specific glyph change, which is tracked separately
- The UI sync parchment misread on attempts 3 and 4. Real, but fallout from this bug rather than a cause, and it should be re-assessed after the surface check lands rather than fixed blind
- Any attempt to make the Map Overlay usable for orders. It is the wrong surface by design
- A survey / observation-only zoomed-out pose

---

## 9. Z2 sweep observations (2026-09-11 live)

Sweep script: `scripts/spike_zoom_surface_sweep.py`  
Run dir: `data/runtime/zoom_surface_sweep/20260911-114746/`  
Committed evidence:

| Frame | Path |
|-------|------|
| Max-in (clean 3D after Home) | [`docs/design/assets/map-overlay-zoom/z2-20260911-00-max-in.jpg`](design/assets/map-overlay-zoom/z2-20260911-00-max-in.jpg) |
| X plateau + toggle banner | [`docs/design/assets/map-overlay-zoom/z2-20260911-50-x-banner.jpg`](design/assets/map-overlay-zoom/z2-20260911-50-x-banner.jpg) |
| Wheel → political overlay | [`docs/design/assets/map-overlay-zoom/z2-20260911-56-wheel-overlay.jpg`](design/assets/map-overlay-zoom/z2-20260911-56-wheel-overlay.jpg) |
| Machine report JSON | [`docs/design/assets/map-overlay-zoom/z2-20260911-114746-report.json`](design/assets/map-overlay-zoom/z2-20260911-114746-report.json) |

| Field | Value |
|-------|-------|
| Window client size | **1280×720** |
| Z1 in-clamp clean? | **Yes** after `Home` + north (earlier pathological half-void without Home) |
| `H` (hazard) | **Two-stage:** (1) **X-key plateau ~35–50** already shows banner *“Keep scrolling to toggle the Map Overlay”* while still on 3D map; (2) **mouse wheel from that plateau opens political Map Overlay by ~press 56** (absolute from max-in, including X steps). Keyboard `zoom_out` alone **does not** open overlay — it clamps with the banner up. |
| `Q` (15–20 px settlement) | **Not auto-locked.** Feature-scale proxy failed (stuck ~1–2). By eye: Arretium remains large/clickable at X plateau (press 50). **Q appears slack vs H** — safe band is wide; canonical can be chosen for reach inside the band once margin is picked. |
| H−Q / Q binding? | Gap large if Q ≪ 35; treat Q as **non-binding** until a measured settlement-px pass. Do **not** pick margin yet. |
| Z3 stats — 3D max-in | var=0.0081 sat=0.658 edges=0.093 luma=0.388 (not overlay) |
| Z3 stats — 3D at X banner (50) | var=0.0060 sat=0.563 edges=0.059 luma=0.300 (not overlay; banner present) |
| Z3 stats — political overlay (56) | var=0.0059 sat=0.475 edges=0.039 luma=0.311 — **provisional Z3 still said textured_map** (translucent overlay keeps terrain texture). Thresholds must be recalibrated (left legend / faction fills), not trusted yet. |
| Date | 2026-09-11 |

**Locked 2026-09-11 after operator fidelity guidance + landed march:** `zoom_steps_from_max_in: 14` (H_banner≈37), Z7 `expected_aabb_width_map: 55.6`, `DEFAULT_ANCHOR_SCALE: 0.0133` @ 1280×720. Flavius was at Arretium (not belief Segesta-near); short west order landed the proof.
