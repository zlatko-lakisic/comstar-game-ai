# In-frame settlement location by detection, not by model

**For an AI coding agent working in the `comstar-game-ai` repo.**

Companion to `settlement_detector.py`, which this document describes, and to
`docs/design/map-window-projection.md`, whose projection path this sits beside
rather than replaces. Follows `canonical-zoom-fix-handoff.md`, which disabled
`map_target_vision` under Z9.

Changes are prefixed `S` so they do not collide with the `C` series in
`campaign-director-handoff.md`, the `P` series in `camera-pose-reset-handoff.md`,
the `F` series in `always-hold-investigation.md` or the `Z` series in
`canonical-zoom-fix-handoff.md`.

Written 2026-09-11.

---

## 0. Rules of engagement

1. **Every constant in the script marked `CAL` is fitted to a single frame.**
   One capture, 1280x720, at one zoom that is not the canonical pose. Treat
   them as a starting point. None of them is a measurement until S5 says so.
2. **The detector locates. It does not decide.** It returns badge positions and
   faction colours. Target selection, stance and reachability live elsewhere and
   are passed in.
3. **Do not reintroduce a coordinate field into any model contract.** See S2.
   A schema that can produce a click point will eventually have one clicked.
4. **Refuse rather than click from an unmeasured offset.** `click_point()`
   raises today and must keep raising until S4 lands. A click on the badge
   selects the plaque, not the settlement.
5. **Detection is per frame, per turn.** Never cache a pixel position across
   turns. The camera and the board both move.
6. **Stop and ask** on anything in section 6.

---

## 1. Why this exists

### 1.1 The vision agent can read, and cannot localise

The `qwen3-vl:8b` probe of 2026-09-11 (`data/runtime/view_besiege/20260911-220517_qwen3vl_raw.txt`)
returned well-formed JSON after the AO 2.10.2 text-extraction fix. Names,
regions and faction colours were correct for all four settlements in frame.

The coordinates in the same response were not usable, and not by a margin that
tuning closes.

| Settlement | Badge centre, measured | Model reported | Miss |
|---|---|---|---|
| Segesta | 0.151, 0.456 | 0.15, 0.45 | ~5 px |
| Arretium | 0.466, 0.628 | 0.45, 0.55 | ~60 px |
| Patavium | 0.570, 0.285 | 0.55, 0.35 | ~54 px |
| Ariminum | 0.699, 0.528 | 0.65, 0.50 | ~66 px |

All eight returned values are multiples of 0.05. Eight independent estimates
landing on one coarse grid is not localisation carrying error, it is the model
emitting round numbers shaped like an answer. Segesta is not a hit, it is the
grid happening to fall on a plaque.

**Quantisation alone disqualifies the output regardless of model quality.** Half
a grid cell is 32 px horizontally and 18 px vertically at this resolution. The
canonical zoom rule in `camera-pose-reset-handoff.md` P1 puts a settlement at 15
to 20 px on screen. The rounding error exceeds the target before any question of
whether the model can see is reached.

So Z9's condition is half satisfied. The agent now returns structured output,
which was the stated bar, but only for the role it is actually good at. Turning
`use_map_vision` back on as a locator would reintroduce what Z9 removed, and this
time it would fail quietly behind valid JSON, which is worse than prose that
fails to parse.

### 1.2 The plaque is not one sprite, and the difference runs the wrong way

Measured on the same frame:

- **Arretium and Ariminum** render a solid cream card with garrison unit icons
  beneath the name.
- **Segesta and Patavium** render a translucent label with no cream fill at all,
  name and region text straight onto terrain.

Both pairs split along badge colour, red and green, which on this frame is also
the owned versus foreign split.

The consequence is the one that matters. A detector keyed on the cream lozenge
body finds only the settlements that render the solid card, which on this
evidence are the ones already owned. That is exactly backwards for an attack
loop. Whether ownership is the cause is open, see section 6 item 1.

**The badge is the only element common to all four**, which is why the detector
keys on it and nothing else.

### 1.3 What the detector does and what it returns

`detect_settlements(img)` masks pixels in each known faction hue band, takes
connected components, and gates them on diameter, roundness, and an annular
test: the faction colour must be present on the rim and must not fill the core.
A badge is a coloured ring around a pale emblem field. A terrain patch bounded
by region border lines is solid through the middle and fails.

Hue bands come from `settlements.FACTION_LEGEND_COLOURS` / campaign UI atlas
legend (saturated only). Live rim samples after `capital_zoom` (Home) refine
Julii red / Gaul green. Scipii blue needs a higher saturation floor than red/
green so seawater does not flood the mask. Low-sat legend fills (Carthage white,
Rebels taupe, Greek olive, …) stay out of `BANDS` until they have a high-S
badge sample.

Armies are excluded structurally rather than by instruction. An army banner is
a tall rectangle beside a walking figure and fails the diameter and roundness
gates. Nothing in this path can be talked out of that by a prompt.

Per hit it returns `faction_colour`, `badge_px`, `badge_d`, and `name_crop`, a
box over the name and region text sitting immediately right of the badge.

### 1.4 Result on the reference frame

Three of four settlements found at exact pixels, zero false positives, roughly
15 ms, no VRAM. Compare 111 s and zero usable points from the model.

Segesta was missed, and the cause is an artefact of the capture rather than the
detector: the debug reticle is composited over its badge in that screenshot.
`host-app-architecture.md` section 2 already makes WGC window capture primary so
overlays are structurally excluded, so this case should not occur in production.
It is untested until S5.

An earlier pass without the annular test also returned a terrain patch at
854,624, where a green field bounded by coloured region borders passed the size
gate. That is the false-positive class this detector has, and the core test is
what closes it. Do not weaken that test.

---

## 2. The changes

### S1. Land the detector as the in-frame locator

Place `settlement_detector.py` under the host app's vision package. It has no
dependency beyond OpenCV and NumPy and no network path.

It is the locator for settlements **visible in the current frame only**. The
map-to-window projection remains the locator for everything off screen. Neither
replaces the other, and the selection between them belongs to the caller.

### S2. Remove `x` and `y` from the `map_target_vision` contract

Delete the fields from the overlay YAML schema and from the wire prompt. Do not
soften them to advisory, do not keep them with a comment.

This is the same failure class as Z4, where a classifier whose label set
excluded a real state returned the nearest wrong answer at usable-looking
confidence. A schema that demands coordinates will always be given plausible
ones.

What remains for the agent is a belief-store observation: name, region, owner
colour, seen this frame. That has no path to the actuator.

### S3. Resolve the anchor contradiction in the prompt

The `map_target_vision` YAML system prompt specifies oval centres. The wire text
specifies a plaque anchor and asks for the centre of that anchor. Two anchor
definitions reach the model in one call, so no answer it gives can be graded.

Fix this even though S2 removes the coordinate fields, because the same
contradiction will otherwise be inherited by whatever replaces them.

### S4. Measure `CLICK_OFFSET_PX`. Blocking

The badge sits at the plaque's left end, and the plaque floats above the
settlement. The clickable thing is the town oval on the ground, roughly 10 to 15
px below and right on the reference frame.

Measure at the canonical pose, not this one. Method: select an army, pick a
known settlement, bisect the offset until the move cursor glyph appears, per the
existing glyph gate. Record the value in `docs/design/map-window-projection.md`
with the window size and the zoom press count, beside `anchor_scale`, because it
is zoom dependent and void if the pose changes for the same reason.

Until this lands `click_point()` raises. Leave it raising.

### S5. Calibrate against a frame set, then record a recall number

Capture at the canonical pose, through the production WGC path so no overlay is
composited. At minimum: one frame per faction colour in play, one frame with a
settlement partially behind terrain, one frame with a settlement that renders no
plaque at all, and one frame containing armies of both colours.

Hand-label badge centres. Tune `BADGE_D_PX`, `D_TOL`, the hue bands and the two
annular thresholds against that set. Record recall, false positives per frame,
and centre error in pixels, with the window size and press count.

A number fitted to a pose that has never produced a working order certifies a
broken pose. That is Z7's rule and it applies here unchanged.

### S6. Stance is an input, never an inference

`rank_targets` takes a colour to stance map and drops any colour not in it.

Colour identifies a faction. Enemy, neutral and ally is a relationship that
changes without the colour changing, so it cannot be read from a frame. Source
it from the diplomacy screen or script telemetry. An unknown colour is not a
target, and must not be mapped to the nearest known band.

### S7. Screen distance is a milestone proxy, and is labelled as one

The campaign map is drawn in perspective, so equal pixel distances are unequal
map distances. A settlement across a mountain range or a strait is near on screen
and far in turns.

Ordering by screen distance is acceptable to land a first attack. It must be
replaced by the pathfinder's turns to reach before it counts as target
selection, which is what the campaign directive contract in
`campaign-director-handoff.md` C3 already expects under `expects.turns_to_reach`.

### S8. The vision agent keeps the reading role, off the critical path

Feed it `name_crop` boxes, get names back, use them to tie a detection to a
settlement id the director can name. Reading text is what it did well.

Try OCR on the same crops first. If OCR handles the game font, the agent is not
needed here at all and 111 s leaves the loop entirely. Either way this never
blocks a move, per `cursor-handoff.md` 4.3.

---

## 3. Order of work

```
S2  strip coordinates from the contract    one line, do it first
S3  fix the anchor contradiction           independent
S1  land the detector                      needs nothing
S4  measure the click offset               blocks any click, needs canonical pose
S5  calibrate and record recall            needs S1 and a frame set
S6  wire the stance map                    needs a telemetry source
S7  ordering, proxy first                  needs S6
S8  name reading on crops                  independent, try OCR before the agent
```

S2 and S3 are one-line and one-paragraph respectively and both shorten the
debugging loop. Do them before anything else even though the detector is the
interesting part.

---

## 4. Acceptance

1. **No model contract can emit a coordinate.** `grep` for `"x"` and `"y"` in
   the overlay agent schemas and the wire prompts returns nothing for
   `map_target_vision`.
2. **The detector is measured, not fitted.** Recall, false positives per frame
   and centre error appear in the design doc with the window size and zoom press
   count, from the S5 frame set, not from the reference frame.
3. **The no-plaque case is characterised.** The frame set includes a settlement
   that renders no plaque, and the documented behaviour is a miss reported as a
   miss, not a nearby badge returned in its place.
4. **A click lands before any offset is written down.** The Flavius to Segesta
   acceptance script is green using a detector-supplied point, and the commit
   recording `CLICK_OFFSET_PX` comes after the commit that proves the march.
5. **`click_point()` still raises without a measured offset.** Deliberately
   clear the constant and confirm the run refuses rather than clicking the badge.
6. **An unknown faction colour is refused.** Introduce a colour absent from the
   stance map and confirm it is dropped from candidates with a logged reason,
   not mapped to the nearest band.
7. **The overlay is absent from captured frames.** Twenty consecutive captures
   through the production path contain no reticle, no legend and no debug text.
   Segesta is detected in at least one of them.
8. **The terrain false positive stays closed.** The 854,624 patch from the
   reference frame is in the regression set and the annular test rejects it.

---

## 5. What worked, and must not be weakened

The annular core test is the only thing separating a badge from a green field
bounded by region borders. Size and roundness both passed that patch.

The same shape of gate is what excludes armies. Neither is expressible as a
prompt instruction, which is the point: the earlier prompt asked the model in
plain English to skip armies, and there was no way to know whether it had.

---

## 6. Stop and ask

1. **What actually drives the solid versus translucent plaque split?** The
   reference frame is consistent with ownership, but hover state, garrison
   visibility and zoom are all untested alternatives, and one frame cannot tell
   them apart. The answer changes nothing in the detector, which keys on the
   badge, but it changes what the `name_crop` box can be relied on to contain.
2. **Do plaques render at the canonical zoom at all?** The reference frame is
   zoomed further in than P1's canonical pose. If plaques disappear or shrink
   past a zoom threshold, the whole approach is pose-bound in a way that has to
   be recorded, and `BADGE_D_PX` has to be re-measured there regardless.
3. **Faction colour collision.** Two hue bands are in use. Rome alone fields
   three player houses in reddish tones, and the bands are coarse enough that
   distinct factions will collide. The badge emblem is far more discriminative
   than the ring colour. Decide whether to template match emblems now or accept
   colour collisions until they bite, and record which.
4. **Is a plaque-derived point good enough, or does the town oval need its own
   detection?** S4 assumes a fixed offset from badge to oval at a fixed pose. If
   the offset turns out to vary with terrain height under the settlement, the
   oval needs detecting directly and S4 changes shape.
