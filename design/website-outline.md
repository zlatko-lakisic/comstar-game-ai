# Project site outline

A GitHub Pages site for Comstar Game AI. This is the plan, not the build.

Written 2026-09-03. Companion to `README.md` and the design set.

---

## 1. What the site is for

Two audiences, and they want different things in the first ten seconds.

| Reader | Wants to know |
|--------|---------------|
| Someone who found the repo | What is this, is it interesting, does it work yet |
| You, checking in | Which phase is live, what is blocked, what is next |

So the site has to answer **two questions above the fold**: what it is, and how far along it is. Everything else is depth for people who want it.

**Be honest about status.** Nothing is built. A site claiming momentum it does not have reads badly and ages worse. A site that says "0 of 7 phases, phase 0 starts next" and then shows the depth of the design behind it is far more convincing, because the design is the actual asset right now.

## 2. Visual system

Carry the identity already established by the overlay mockup, so the site, the mockup and the hero image read as one thing.

| | |
|---|---|
| Ground | Warm-biased near-black, `#0c1012`, panels `#141a1d`, rules `#232c31` |
| Accent | Pale cyan `#5fd0e0`, deep `#2b8b9c`. Machine layer, used sparingly |
| Semantic | `#7fc08a` done, `#e8a33d` in progress, `#e0685f` blocked, `#5d6a72` not started |
| Display and body | IBM Plex Sans |
| Data, labels, phase numbers | IBM Plex Mono |
| Roman accent | Cinzel, three or four words on the whole site, no more |

Committing to a single dark theme is right here. The hero is a dusk battlefield and the mockup is a dark screen; a light mode would fight both.

## 3. The vertical progress rail

The distinctive interaction, so it should do real work rather than decorate.

### Position and behaviour

- Fixed to the left edge, roughly 56px wide, full viewport height
- A 2px vertical track with a cyan fill that grows with scroll position
- Section nodes sit at their proportional position on the track
- The active node grows and reveals its label beside it
- Nodes are real anchor links, so keyboard and screen reader navigation work and it is not a JS-only device
- Below 900px viewport width it collapses to a 3px progress line across the top

### Two options for what the rail carries. Open for decision.

**Option A, separated.** The rail is scroll position with section nodes, and build progress lives only in the phase tracker section. A small fixed cap at the top of the rail shows `0/7` as a constant. Simple, predictable, easy to build.

**Option B, the rail becomes the timeline.** The rail's upper half carries the narrative sections. As you scroll into the build section, the nodes become the seven phases and the active phase highlights, each coloured by its status. The rail transitions from "where am I in the document" to "where are we in the build", which mirrors the page's own structure.

B is better if it works, and it is more work. My recommendation is B, but it is your call.

### What the rail must not do

Not a reading-time estimate, not a percentage of the article consumed, not animated on load. It is a position indicator and a navigation control.

## 4. Page outline

### Section 1. Hero

- Full-bleed `aerial-dust-hero-2560x1097.jpg`, darkened toward the upper left where the type sits
- Title, then one line: *An opponent for Total War: Rome Remastered that plays the game rather than cheating at it*
- A status chip, monospaced, high contrast: `NEXT UP · PHASE 0 OF 7 · PRECONDITIONS AND CAPTURE`
- Two links only: the repo, and jump to the build tracker
- Sized to content, not `100vh`, so the next section is visible at rest

### Section 2. The question

Short, wide measure, no image. The Total War AI cheats and every player knows it, which takes something out of the win. So: can you build an opponent that is hard to beat without giving it anything a human does not have?

This is the thesis. It should be readable in fifteen seconds.

### Section 3. What it is

Three or four sentences, plus one diagram: game and host app on the Windows box, AO engine and model on `ada`, a single Reach WebSocket between them, and a note that the game process is the host and AO is a service it consults.

Call out the three things it does not do: no memory reading, no process injection, no cheat commands.

### Section 4. The three ideas

The most quotable part of the site. Three blocks, each with a visual.

| Idea | Visual |
|------|--------|
| Time stops so the machine can think | The freeze cycle as a small loop diagram: freeze, read, decide, order, resume |
| The model picks the objective, not the moves | The battle intent JSON, syntax-coloured, small |
| Nobody writes down what a good move is | The list of engine-computed outcome signals, `dump_fac_score`, `UnitHasRouted`, casualties, ranking |

### Section 5. What is being built

The component map. This is the step-back view.

Grouped by process, each component a row: name, one line on what it does, the phase that builds it, and a status pill. Driven by `_data/components.yml` so it never drifts from the phase tracker.

```
Process A  Game I/O          capture · actuator · console · log tailers · state machine · kill switch
Process B  Agent runtime     belief store · predictors · view compositor · Reach client
Process C  Overlay UI        glow · keyboard · cursor · AO cycle window
On ada     AO engine         session overlay · seven client agents · corpora
```

Include the overlay mockup here as an embedded still, linking to the live HTML version.

### Section 6. Build tracker

The section the rail points at, and the reason the site exists for you rather than for a visitor.

Seven phases as a vertical stepper. Each row carries:

- Phase number in mono, large
- Name and a one-line summary
- **The acceptance test**, verbatim from the handoff. This is the interesting part and most project sites omit it, because most projects do not have one
- Status pill, coloured semantically
- Blocked phases show what they are blocked on, as a link to the open question

Phase 7 shows `BLOCKED · write path into AO's knowledge base`. Displaying that honestly is more credible than hiding it.

Above the stepper, one summary line: `0 of 7 complete · 1 blocked · phase 0 next`.

### Section 7. The rules it plays by

The fair play table: fog of war, no cheats ever, declares intent, single player only. Then the one advantage it does take, which is that it freezes and micros every unit on every tick, stated plainly as a deliberate choice with a configurable dial.

This section does a lot of work for credibility. Lead with the constraints, not the capabilities.

### Section 8. The hard part

Windows lies to you. `SendInput` blocked by UIPI returns success and does nothing, and Microsoft document that neither the return value nor `GetLastError` will tell you. Then the other silent failures, briefly.

Close on the consequence: every action is declare, execute, verify, retry. Not because it is elegant, because the alternative is a system that appears to work.

Use `wide-landscape-16x9-1920x1080.jpg` here if the page needs a second image. Its flat annotation style matches the mockup better than the hero does, which gives the page two registers rather than one repeated.

### Section 9. Built on Agentic Orchestration

Three cards: the engine, the Reach SDK, Feral's modding documentation. One line each on the role it plays. Real links.

### Section 10. The design set

Index of the nine documents with a line each. These are the actual artifact right now, so give them room rather than burying them in a footer.

### Section 11. Open questions

Live list from the handoff, six of them, each with what it blocks. Ends the page on candour rather than a call to action, which suits a project with nothing shipped.

### Footer

Apache-2.0. Not affiliated with Creative Assembly, Feral Interactive or SEGA.

## 5. The data model

The point of this is that updating progress is a one-line edit, never a markup edit.

`_data/phases.yml`

```yaml
current_phase: 0
phases:
  - id: 0
    name: Preconditions and capture
    summary: Window detection, WGC window capture, ring buffer, three startup self tests
    accepts: Self tests pass and frames capture with the overlay stub absent from them
    status: not_started          # not_started | in_progress | done | blocked
    blocked_by: null
  - id: 7
    name: Learning
    summary: After action records, corpus, consolidation
    accepts: Records written and retrievable, consolidation produces doctrine
    status: blocked
    blocked_by: write-path        # anchor into the open questions section
```

`_data/components.yml`

```yaml
- group: Process A
  subtitle: Game I/O
  items:
    - name: WGC window capture
      does: Captures the game window, excludes everything drawn on top
      phase: 0
```

`_data/questions.yml` for the open list, each with `id`, `question`, `blocks`.

Status pills, the summary line, the rail node colours and the hero chip all derive from these three files. Nothing is written twice.

## 6. Technical approach

**Recommended: Jekyll**, which GitHub Pages builds natively with no CI. One layout, Liquid loops over `_data`, a single stylesheet, one small script for the rail. No Node, no build step, no `gh-pages` branch to maintain.

**Alternative: a single hand-written HTML file.** Faster to stand up, and every progress update becomes a markup edit, which is the thing the data model exists to avoid. Reasonable only if the site never changes.

The rail script should be small and dependency-free: an `IntersectionObserver` for active section, and a scroll listener throttled with `requestAnimationFrame` for the fill. No framework, no library.

Respect `prefers-reduced-motion` for the fill transition and any scroll-into-view behaviour.

## 7. Assets

| File | Use |
|------|-----|
| `aerial-dust-hero-2560x1097.jpg` | Hero |
| `aerial-dust-og-1200x630.jpg` | Open Graph and Twitter card |
| `wide-landscape-16x9-1920x1080.jpg` | Second image, section 8 |
| `overlay-screen.png` | Section 5, linking to the live mockup |

Serve the hero at 2560 wide with a `srcset` down to 1280, since it is the largest thing on the page.

## 8. Maintaining it

When a phase moves, edit one line in `_data/phases.yml`. The hero chip, the summary line, the stepper, the rail colours and the component statuses all follow.

When a question is answered, remove it from `_data/questions.yml` and clear the `blocked_by` on any phase pointing at it.

That is the whole maintenance surface. If updating progress ever requires touching a template, the data model has a gap.

## 9. Open decisions

1. **Rail option A or B**, per section 3
2. Whether section 6 shows the acceptance tests in full or behind a disclosure, since they are the most interesting content and also the longest
3. Whether to include a short changelog section, which is worth it only if you intend to keep it current
4. Domain: `zlatko-lakisic.github.io/comstar-game-ai` or a custom domain
