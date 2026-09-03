# Comstar Game AI website: build handoff

**For an AI coding agent. Read this file completely before writing anything.**

This builds the project's public site. Every design decision here has already been made. Your job is to implement it exactly, not to improve it.

There is a reference implementation: `site-preview-reference.html`. It is a working, rendered page containing the final tokens, typography, rail, hero, and four of the eleven sections. **Where this document and the reference file agree, both are binding. Where they disagree, this document wins.** Where this document specifies a section the reference does not contain, build it to the spec here in the reference's established style.

Written 2026-09-03. Companion to `website-outline.md` and `cursor-handoff.md`.

---

## 0. Rules of engagement

1. **Do not redesign.** Colours, fonts, spacing, radii, section order and copy are all pinned below. Do not substitute "better" values.
2. **Do not invent copy.** Every user-visible string is either given verbatim in section 8 of this document or comes from a `_data` file. If you need a string that is not here, stop and ask.
3. **Do not add sections, features, or pages.** The site is one page. Section 14 lists what must not be built.
4. **Do not add dependencies.** No npm, no Node, no bundler, no Tailwind, no framework, no CSS preprocessor, no icon library, no animation library, no analytics. The site is Jekyll's own Liquid templating, one hand-written stylesheet, and one hand-written script.
5. **Do not hardcode status.** Phase status, component status, open questions and the document index all come from `_data`. Any status string typed directly into markup is a bug, even if it is currently correct.
6. **Stop and ask** if you hit anything in section 15.

---

## 1. What is being built

A single-page static site on GitHub Pages describing the Comstar Game AI project and showing how far along the build is.

| | |
|---|---|
| Repo | `github.com/zlatko-lakisic/comstar-game-ai` |
| Published at | `https://zlatko-lakisic.github.io/comstar-game-ai/` |
| Build | GitHub Pages native Jekyll. Branch `main`, folder `/` (root). No Actions workflow, no `gh-pages` branch |
| Pages | One. `index.html`. There is no second page and no navigation menu |
| Theme | Single dark theme. No light mode, no theme toggle |

The site has two readers and must serve both above the fold: someone who found the repo and wants to know what this is, and the project owner who wants to know which phase is live.

**Be honest about status.** Nothing is built yet. The site says `0 of 7 phases` and shows the design depth behind it. Do not soften this, do not add "coming soon" language, and do not add a progress percentage that implies motion that does not exist.

---

## 2. Repository layout

Create exactly this. No other files.

```
comstar-game-ai/
├── _config.yml
├── Gemfile
├── .gitignore
├── index.html
├── README.md                        # already exists, do not rewrite
├── _layouts/
│   └── default.html
├── _includes/
│   ├── rail.html
│   ├── s01-hero.html
│   ├── s02-question.html
│   ├── s03-what-it-is.html
│   ├── s04-three-ideas.html
│   ├── s05-components.html
│   ├── s06-tracker.html
│   ├── s07-rules.html
│   ├── s08-hard-part.html
│   ├── s09-built-on.html
│   ├── s10-design-set.html
│   ├── s11-open-questions.html
│   └── footer.html
├── _data/
│   ├── phases.yml
│   ├── components.yml
│   ├── questions.yml
│   └── docs.yml
├── assets/
│   ├── css/
│   │   └── main.css
│   ├── js/
│   │   └── rail.js
│   └── img/
│       ├── hero-2560.jpg
│       ├── hero-1280.jpg
│       ├── og-1200x630.jpg
│       ├── annotation-1920.jpg
│       ├── overlay-screen.png
│       └── favicon.svg
└── design/                          # reference only, excluded from the build
    └── site-preview-reference.html
```

### 2.1 `_config.yml`

```yaml
title: Comstar Game AI
tagline: An opponent for Total War Rome Remastered that plays the game rather than cheating at it
description: >-
  A fogged, no-cheat AI opponent for Total War: Rome Remastered, reasoning
  through Agentic Orchestration and acting through the same console and input
  surface a person uses. Design complete, build not started.
url: "https://zlatko-lakisic.github.io"
baseurl: "/comstar-game-ai"
repo_url: "https://github.com/zlatko-lakisic/comstar-game-ai"
ao_url: "https://github.com/zlatko-lakisic/agentic-orchestration"
reach_url: "https://github.com/zlatko-lakisic/agentic-orchestration-reach"
feral_url: "https://github.com/FeralInteractive/romeremastered"

plugins: []

exclude:
  - design/
  - Gemfile
  - Gemfile.lock
  - vendor/
  - README.md
```

### 2.2 `Gemfile`

```ruby
source "https://rubygems.org"
gem "github-pages", group: :jekyll_plugins
```

### 2.3 `.gitignore`

```
_site/
.jekyll-cache/
.sass-cache/
Gemfile.lock
vendor/
```

### 2.4 The `baseurl` trap

The site is served from a project path, not a domain root. **Every internal URL must go through Liquid.** A hardcoded `/assets/css/main.css` will 404 in production while working locally, which is the single most likely way to ship this broken.

| Correct | Wrong |
|---------|-------|
| `{{ '/assets/css/main.css' \| relative_url }}` | `/assets/css/main.css` |
| `{{ '/assets/img/hero-2560.jpg' \| relative_url }}` | `assets/img/hero-2560.jpg` |
| `{{ '/' \| absolute_url }}` for `og:url` | any literal domain |

In-page anchors (`#tracker`) are the exception and stay bare.

---

## 3. Design tokens

Copy this block into the top of `assets/css/main.css` verbatim. Do not add tokens, rename them, or change a value.

```css
:root{
  --ground:#0c1012;
  --panel:#141a1d;
  --panel-2:#1a2226;
  --rule:#232c31;
  --rule-soft:#1c2427;
  --ink:#e9eef0;
  --ink-dim:#9aa9ae;
  --ink-faint:#5d6a72;
  --accent:#5fd0e0;
  --accent-deep:#2b8b9c;
  --accent-wash:rgba(95,208,224,0.10);
  --done:#7fc08a;
  --progress:#e8a33d;
  --blocked:#e0685f;
  --not-started:#5d6a72;
  --font-display:"IBM Plex Sans",system-ui,sans-serif;
  --font-mono:"IBM Plex Mono",ui-monospace,"SF Mono",Consolas,monospace;
  --font-roman:"Cinzel",serif;
}
```

### 3.1 Colour rules

- `--accent` is the machine layer. It is used for eyebrows, active rail state, links, code strings, and accepted-test labels. It is **not** used for large fills or for body text.
- The four semantic colours encode build status **only**. Never use `--done` for a checkmark that is not a phase status, and never use `--accent` for a status.
- `--ink-faint` and `--not-started` are the same hex on purpose. Use `--not-started` in status contexts and `--ink-faint` in typographic contexts, so a future change to one does not silently move the other.
- The page has exactly three gradients: the two hero scrims (section 8.1) and the rail fill. No other gradient anywhere.

### 3.2 Typography

One stylesheet link in `<head>`, exactly this URL:

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Cinzel:wght@600&family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap">
```

No `@import`. No self-hosted fonts. No additional weights.

| Role | Face | Size | Weight |
|------|------|------|--------|
| Hero h1 | Plex Sans | `clamp(2.1rem, 4.4vw, 3.15rem)`, line-height 1.08 | 600 |
| Section h2 | Plex Sans | 1.9rem | 600 |
| Card / phase h3 | Plex Sans | 1.02–1.05rem | 600 |
| Thesis line | Plex Sans | 1.28rem, line-height 1.5, max-width 30ch | 500 |
| Body | Plex Sans | 1rem, line-height 1.6, max-width 64ch | 400 |
| Hero tagline | Plex Sans | 1.08rem, max-width 52ch | 400 |
| Eyebrow | Plex Mono | 0.72rem, `letter-spacing:0.14em`, uppercase, `--accent` | 400 |
| Status pill | Plex Mono | 0.66rem, `letter-spacing:0.05em`, uppercase | 400 |
| Phase number | Plex Mono | 1.5rem | 500 |
| Table header | Plex Mono | 0.68rem, `letter-spacing:0.06em`, uppercase, `--ink-faint` | 500 |
| Code / inline identifiers | Plex Mono | 0.72–0.76rem in blocks, inherit size inline | 400 |
| Wordmark | Cinzel | 0.92rem, `letter-spacing:0.08em`, uppercase | 600 |

**Cinzel appears exactly once on the whole site**: the word `Comstar` in the hero wordmark. Do not use it for headings, the footer, or anything else.

Body copy carries `text-wrap: balance` on `h1, h2, h3` only.

### 3.3 Spacing, radii, borders

| Token | Value |
|-------|-------|
| Section vertical padding | 88px desktop, 56px at ≤640px |
| Section horizontal padding | 32px |
| Prose container | `max-width:740px`, centred |
| Wide container (tracker, components) | `max-width:960px`, centred |
| Radius: pills and chips | 3px (pills 20px, they are lozenges) |
| Radius: panels, code blocks, notes | 4px |
| Radius: the ideas grid container | 6px |
| Radius: rail nodes, dots | 50% |
| Border | Always `1px solid var(--rule)` unless a rule below says otherwise |
| Accent edge (accept blocks) | `border-left:2px solid var(--accent-deep)` |

**Not everything is a card.** Panels are used for: the three idea cells, the accept blocks, the code block, the signal rows, the edge note, and the AO cards. Prose sections, tables and the phase stepper have no panel background. Do not wrap sections in cards.

---

## 4. Layout shell

```
┌──────┬───────────────────────────────────────────────┐
│ rail │  main                                          │
│ 56px │  sections, each centred inside its container   │
│fixed │                                                │
└──────┴───────────────────────────────────────────────┘
```

- `.rail` is `position:fixed; left:0; top:0; width:56px; height:100vh; z-index:40`.
- `main` carries `margin-left:56px`.
- Breakpoints, and there are only three: **900px** (rail collapses, `main` margin clears), **820px** (ideas grid goes single column), **640px** (section padding reduces). Do not add others.
- `body` carries `overflow-x:hidden`. Nothing may cause horizontal page scroll. Wide content scrolls inside its own `overflow-x:auto` container.

---

## 5. The rail

The distinctive interaction. Build it exactly as specified; it is not a place for improvement.

### 5.1 Structure

```
.rail
├── .rail-cap            static "0 / 7", never animates, never updates on scroll
└── .rail-track-wrap     2px wide, --rule background, flex:1
    ├── .rail-fill       absolute, height driven by scroll progress
    └── .rail-nodes      absolute, holds the anchor nodes
        └── a.rail-node × 8
            └── .rail-label
```

### 5.2 The cap

Renders build progress, not scroll progress. Three stacked elements: the completed count in `--accent`, a 14×1px `--rule` divider, the total in `--ink-faint`. Both numbers come from `_data/phases.yml` (section 7.1), never typed:

```liquid
{% assign done = site.data.phases.phases | where: "status", "done" | size %}
```

It is **constant**. It does not react to scrolling.

### 5.3 The fill

`height` is a percentage of document scroll progress: `scrollTop / (scrollHeight - innerHeight)`, clamped 0–1. Background `linear-gradient(180deg, var(--accent-deep), var(--accent))`. Transition `height 0.12s linear`.

### 5.4 The nodes

Eight nodes, evenly distributed down the track by index (`i / (n-1) × trackHeight`), not by section height. They are real `<a href="#id">` anchors so keyboard and screen-reader navigation work without JavaScript.

| # | Anchor | Label |
|---|--------|-------|
| 1 | `#hero` | `Comstar` |
| 2 | `#question` | `The question` |
| 3 | `#what-it-is` | `What it is` |
| 4 | `#ideas` | `Three ideas` |
| 5 | `#components` | `Components` |
| 6 | `#tracker` | `Build tracker` |
| 7 | `#rules` | `The rules` |
| 8 | `#reference` | `Reference` |

Node 8 targets the "Built on Agentic Orchestration" section, which is the top of the reference block (sections 9, 10, 11 and the footer). There is no node for sections 8, 10 or 11 — eight nodes is the maximum the 56px rail carries legibly.

**States.** Resting: 9×9px, `--ground` fill, 2px `--ink-faint` border, label at `opacity:0`. Active: 13×13px, `--accent` fill and border, `box-shadow:0 0 0 4px var(--accent-wash)`, label visible in `--accent`. Label also becomes visible on `:hover` and `:focus-visible`.

**Active detection.** One `IntersectionObserver` over the eight target sections, `rootMargin: '-45% 0px -45% 0px'`, `threshold: 0`. On intersect, clear `.active` from all nodes and set it on the matching one. Do not compute active state from scroll offsets.

**Throttling.** The scroll listener updates the fill inside a `requestAnimationFrame`, guarded by a `ticking` boolean, registered `{passive: true}`. Do not use a timer, a library, or an unthrottled handler.

### 5.5 Below 900px

The rail becomes a **3px horizontal progress line fixed across the top** of the viewport. The cap and all nodes are `display:none`. The fill drives `width` instead of `height`. `main` loses its left margin and gains `margin-top:3px`. There is no hamburger menu, no mobile nav, and no replacement for the node labels.

### 5.6 What the rail must not do

Not a reading-time estimate. Not a percentage-read indicator. Not animated on load. It does not scroll-hijack, it does not snap, and it does not change the seven-phase status colours — that is the tracker's job, not the rail's.

`assets/js/rail.js` is the only script on the site. Budget: under 3 KB unminified. No other JavaScript may be added.

---

## 6. Section order and IDs

Exactly eleven sections plus a footer, in this order. Each is its own include, each sets its own `id`.

| # | `id` | Include | Container | Rail node |
|---|------|---------|-----------|-----------|
| 1 | `hero` | `s01-hero.html` | full bleed | 1 |
| 2 | `question` | `s02-question.html` | prose 740 | 2 |
| 3 | `what-it-is` | `s03-what-it-is.html` | prose 740 | 3 |
| 4 | `ideas` | `s04-three-ideas.html` | prose 740 | 4 |
| 5 | `components` | `s05-components.html` | wide 960 | 5 |
| 6 | `tracker` | `s06-tracker.html` | wide 960 | 6 |
| 7 | `rules` | `s07-rules.html` | prose 740 | 7 |
| 8 | `hard-part` | `s08-hard-part.html` | prose 740 | — |
| 9 | `reference` | `s09-built-on.html` | prose 740 | 8 |
| 10 | `design-set` | `s10-design-set.html` | prose 740 | — |
| 11 | `open-questions` | `s11-open-questions.html` | prose 740 | — |
| — | `foot` | `footer.html` | prose 740 | — |

`index.html` is nothing but front matter and eleven `{% include %}` lines plus the footer. No content lives in `index.html`.

---

## 7. The data files

The whole point: **updating progress is a one-line edit and never touches markup.** If a status change requires editing a template, the data model has a gap and you have built it wrong.

### 7.1 `_data/phases.yml`

Complete file. Ship it exactly like this — these are the real current values.

```yaml
current_phase: 0
total: 7
phases:
  - id: 0
    name: Preconditions and capture
    summary: Window detection, WGC window capture of the game window, ring buffer, all three startup self tests.
    accepts: Self tests pass, frames captured at target rate with the overlay stub absent from them.
    status: not_started
    blocked_by: null
  - id: 1
    name: Observation
    summary: Background script emitting state and transitions, log tailers, console query channel, belief store with provenance, age and confidence.
    accepts: Campaign state reconstructed externally and matching the screen for 20 consecutive turns. No AI involved.
    status: not_started
    blocked_by: null
  - id: 2
    name: Actuation
    summary: Console wrapper with the fair play gate, SendInput actuator with dwell and hover, diff based order computation, verification tiers, intent record.
    accepts: 20 consecutive turns driven end to end, hardcoded, no reasoning, zero desyncs between intended and actual.
    status: not_started
    blocked_by: null
  - id: 3
    name: Overlay
    summary: Process C, four surfaces, event stream, takeover handshake, three control transitions.
    accepts: Capture exclusion, click through and non activation self tests all pass with the full overlay live. Kill switch releases everything from any state.
    status: not_started
    blocked_by: null
  - id: 4
    name: Battle loop
    summary: toggle_game_update freeze cycle, output_unit_positions parse, deployment phase handling, post battle harvest.
    accepts: A complete battle fought at a fixed tick with no manual intervention, and an after action record written.
    status: not_started
    blocked_by: null
  - id: 5
    name: Deterministic predictors
    summary: "Built from Battle_and_Campaign_Formulae.md: melee and charge resolution, fatigue and morale, auto resolve estimate, siege duration, economy projection, movement reachability."
    accepts: Every predictor output paired with an observed outcome in the log.
    status: not_started
    blocked_by: null
  - id: 6
    name: AO integration
    summary: Reach session overlay, mTLS enrolment, direct_agent calls, view compositor, neutral directive fallback, cancellation on stale.
    accepts: Directives influence play, a move is never blocked, every failure path resolves to neutral.
    status: not_started
    blocked_by: null
  - id: 7
    name: Learning
    summary: After action records, the experience corpus, offline consolidation into doctrine.
    accepts: Records written and retrievable, consolidation produces doctrine.
    status: blocked
    blocked_by: write-path
```

**`status` is one of exactly four values**: `not_started`, `in_progress`, `done`, `blocked`. `blocked_by` is either `null` or a question `id` from `questions.yml`, which becomes an anchor into section 11.

### 7.2 `_data/components.yml`

```yaml
- group: Process A
  subtitle: Game I/O. Owns the kill switch, never allowed to stall
  items:
    - name: WGC window capture
      does: Captures the game window, excludes everything drawn on top of it
      phase: 0
    - name: Ring buffer and frame selection
      does: Keeps recent frames so the selector can look backwards after an event
      phase: 0
    - name: SendInput actuator
      does: Synthetic mouse and keyboard, with dwell, hover and diff based ordering
      phase: 2
    - name: RomeShell console channel
      does: Text commands where clicking would be imprecise, behind the fair play gate
      phase: 2
    - name: Log tailers
      does: Reads scripting_log.txt and message_log.txt as they are written
      phase: 1
    - name: Game state machine
      does: Asserts the expected screen before any action executes
      phase: 1
    - name: Control state machine
      does: Take over, hand back, kill. All three are hotkeys
      phase: 3
    - name: Intent record writer
      does: Logs declare, execute, observe for every action taken
      phase: 2

- group: Process B
  subtitle: Agent runtime. Allowed to stall
  items:
    - name: Belief store
      does: What the agent thinks is true, with provenance, age and decaying confidence
      phase: 1
    - name: Deterministic predictors
      does: One step forward predictions built from the published combat formulae
      phase: 5
    - name: View compositor
      does: Builds small composed images from the pieces that carry decision relevant information
      phase: 6
    - name: Reach client
      does: The only path to AO. Carries intent and belief, never pixels and clicks
      phase: 6

- group: Process C
  subtitle: Overlay UI. Allowed to crash
  items:
    - name: Edge glow
      does: Colour coded state around the game window, with a text chip naming it
      phase: 3
    - name: Virtual keyboard
      does: Only the keys the agent uses, fading in on press
      phase: 3
    - name: Cursor indicator
      does: Ring and trail, with a marker showing where it intends to go before it moves
      phase: 3
    - name: AO cycle window
      does: Request, live status, directive, and the verification result
      phase: 3

- group: On ada
  subtitle: The engine and the model, on the same LAN
  items:
    - name: AO session overlay
      does: Seven ephemeral client agents registered for the run
      phase: 6
    - name: The model
      does: One local model, two prompt modes. Tactical is terse, strategic may reason
      phase: 6
    - name: The corpora
      does: Doctrine and experience, both on AO
      phase: 7
```

### 7.3 `_data/questions.yml`

```yaml
- id: write-path
  question: What is the write path into AO's knowledge base?
  detail: Both corpora live on AO and the consolidator writes doctrine directly, but Reach exposes no write path. Candidates are an engine HTTP ingest route, a shared filesystem on ada, a custom tool deployed via the sandbox client, or an agent side write tool.
  blocks: Phase 7
- id: rag-restriction
  question: Can direct_agent be restricted to specific rag sources?
  detail: The observable and privileged split depends on it, and the whole play loop uses direct_agent rather than the planner. Unverified against the engine.
  blocks: Phase 7
- id: plays
  question: Are parameterised plays adopted?
  detail: Multi step patterns such as hammer and anvil, refused flank and feigned retreat, selected by the model and executed by the reactive layer. Proposed as the mitigation for having no tree search. Not adopted.
  blocks: Phases 4 and 6
- id: campaign-tunnel
  question: Does campaign_director need the game_query tunnel?
  detail: Or is a composed brief plus retrieval enough. Fewer tool round trips is materially faster on a local model.
  blocks: Phase 6
- id: fold-modeler
  question: Should opponent_modeler fold into campaign_director?
  detail: Saves a call, costs a bigger prompt and a mixed output contract.
  blocks: Phase 6
- id: overlay-taste
  question: The remaining overlay taste calls
  detail: Trail length and decay, keyboard placement, whether held modifiers render differently from taps, chat scrollback depth, and whether the full directive is expandable.
  blocks: Phase 3
```

### 7.4 `_data/docs.yml`

```yaml
- name: cursor-handoff.md
  does: The build brief. Constraints, architecture, build order, open questions
- name: decisions.md
  does: Twelve architecture decisions with their consequences, and the risk register
- name: working-agreement.md
  does: Roles, the decision rule, the label key
- name: rtw-remastered-integration.md
  does: Observation channels, actuation tiers, game state machine, fair play boundary
- name: host-app-architecture.md
  does: Capture, input injection, process split, safety layer
- name: host-overlay-ui.md
  does: The on screen overlay, and how it stays out of the screenshots
- name: reach-overlay-design.md
  does: Session overlay, run modes, connection config, call patterns
- name: bottlenecks.md
  does: Eight constraints with the arithmetic behind each
- name: smart-player-architecture.md
  does: The general design this one specialises
- name: agentic-orchestration-platform-context.md
  does: AO and AO Reach reference
```

---

## 8. The sections, one by one

Copy below is **verbatim**. Do not reword, do not "tighten", do not add a call to action.

### 8.1 Section 1 — Hero

Full bleed, `min-height:640px`, **not** `100vh`. The next section must be partly visible at rest.

**Image handling differs from the reference file.** The reference uses a CSS background for portability. The real site uses a responsive `<img>`:

```html
<img class="hero-img"
     src="{{ '/assets/img/hero-2560.jpg' | relative_url }}"
     srcset="{{ '/assets/img/hero-1280.jpg' | relative_url }} 1280w,
             {{ '/assets/img/hero-2560.jpg' | relative_url }} 2560w"
     sizes="100vw"
     alt="A Roman legion in battle formation on a dry plain, with a thin cyan diagrammatic layer annotating the formations and tracing an arc toward the enemy's exposed left flank"
     width="2560" height="1097" fetchpriority="high">
```

`.hero-img` is `position:absolute; inset:0; width:100%; height:100%; object-fit:cover; object-position:center 42%;`. It is **not** lazy loaded. Two scrims sit above it as a single absolutely positioned `.hero-scrim` element:

```css
background-image:
  linear-gradient(115deg, rgba(9,12,13,0.94) 0%, rgba(9,12,13,0.72) 32%, rgba(9,12,13,0.18) 58%, rgba(9,12,13,0.34) 100%),
  linear-gradient(0deg, rgba(9,12,13,0.55) 0%, rgba(9,12,13,0) 40%);
```

Content sits above both, `max-width:680px`, padded `56px 40px 48px`, aligned to the bottom-left.

**Wordmark row:** the word `Comstar` in Cinzel, `--accent`, uppercase; a 20×1px `--accent-deep` divider; the eyebrow `Game AI`.

**h1**, with the line break exactly where shown:

> An opponent that plays Rome
> rather than cheating at it.

**Tagline:**

> A fogged, no-cheat AI faction for Total War: Rome Remastered, reasoning through Agentic Orchestration and acting through the same console and input surface a person uses.

**Status chip.** Mono, bordered `--accent-deep`, background `rgba(20,26,29,0.78)`, with a leading 7px dot coloured by the current phase's status. The text is **generated from data**, never typed:

```liquid
{% assign p = site.data.phases.phases | where: "id", site.data.phases.current_phase | first %}
{% assign done = site.data.phases.phases | where: "status", "done" | size %}
```

Chip format, uppercase, `&middot;` separators:

`NEXT UP · PHASE {{ p.id }} OF {{ site.data.phases.total }} · {{ p.name | upcase }}`

When the current phase's status is `in_progress`, the leading word becomes `IN PROGRESS` instead of `NEXT UP`. When it is `done`, `COMPLETE`. Implement all three branches; only `NEXT UP` renders today.

The chip must wrap on narrow screens. Do not use `&nbsp;` inside it — it causes horizontal overflow at 390px.

**Two links only.** `View the repo →` pointing at `site.repo_url`, and `Jump to build tracker ↓` pointing at `#tracker`. Use the HTML entities `&#8594;` and `&#8595;`, not literal arrow characters. No third link, no button, no email capture.

### 8.2 Section 2 — The question

Eyebrow `THE QUESTION`. No h2. Three paragraphs; the first is the thesis line at 1.28rem, `--ink`, `max-width:30ch`.

> Every Total War player knows the AI cheats, and knowing it takes something out of the win.

> You bait it into a river crossing and it walks in anyway. You leave a city undefended for fifteen turns and nobody comes. When it does beat you, it usually had a resource bonus to do it with.

> So the question here is narrow: **can you build an opponent that is hard to beat without giving it anything a human does not have?** Not fog of war switched off and a gold cheat running — one that sees what you see, learns from what happens, and has to earn it.

Bold spans exactly where marked, using `<strong>` in `--ink`.

### 8.3 Section 3 — What it is

Eyebrow `WHAT IT IS`. h2: `The shape of it`.

Two paragraphs:

> A local application on a Windows machine reads Rome Remastered through its own scripting and console interfaces, drives it with synthetic keyboard and mouse, and consults a language model for strategy through Agentic Orchestration running on a second box.

> The game process is the host and AO is a service it consults, never the other way around. A move is never blocked waiting on a model — a timeout, an error or a malformed response all resolve to a neutral directive and play continues.

**Then a diagram.** Build it in HTML and CSS, not SVG, not an image. Two panels side by side with a labelled connector between them; stacks vertically below 820px.

```
┌─────────────────────────────┐        ┌──────────────────────────────┐
│ WINDOWS BOX                 │        │ ADA SERVER                   │
│                             │        │                              │
│ Total War: Rome Remastered  │◄──────►│ AO engine  :8765             │
│ Process A · game I/O        │  Reach │ The model · RTX 4000 Ada     │
│ Process B · agent runtime   │  mTLS  │ Doctrine and experience      │
│ Process C · overlay UI      │        │                              │
└─────────────────────────────┘        └──────────────────────────────┘
```

Panel headers are mono, 0.68rem, uppercase, `--ink-faint`, tracked `0.06em`. Rows are 0.86rem `--ink-dim`, with the leading name in `--ink`. The connector is a 1px `--rule` line with the mono label `Reach · WebSocket · mTLS` in `--accent-deep` sitting on it; below 820px it becomes a vertical line.

Then three mono chips in a row, `--ink-faint` text, `--rule` border, 3px radius:

`NO MEMORY READING`  `NO PROCESS INJECTION`  `NO CHEAT COMMANDS`

### 8.4 Section 4 — Three ideas

Eyebrow `THREE IDEAS`. h2: `What makes it work`.

A three-column grid, `gap:1px` on a `--rule` background so the gaps read as hairlines, container radius 6px with `overflow:hidden`, cells `--panel`. Single column below 820px. Each cell is title, then a visual, then a paragraph.

**Cell 1.** Title: `Time stops so the machine can think`

Visual: the freeze cycle as an inline SVG, `viewBox="0 0 120 90"`. Five 9px-radius circles at `(60,16) (86,34) (86,60) (60,76) (34,60)` labelled `FREEZE READ DECIDE ORDER RESUME` in 6.4px mono. An arc path connects them clockwise with an arrow marker. The `FREEZE` node is filled `--accent`; the rest are `--panel-2` with `--accent-deep` stroke. Every shape gets an explicit fill. No animation. `role="img"` with `aria-label="Freeze, read, decide, order, resume cycle"`.

Body:

> `toggle_game_update` freezes the battle sim, turning a real-time fight into an effectively turn-based one. The agent thinks in seconds; the battle never notices.

**Cell 2.** Title: `The model picks the objective, not the moves`

Visual: a code block, `--panel-2` background, 0.72rem mono, hand-spanned colouring — keys `--ink-dim`, strings `--accent`, numbers and booleans `--progress`, punctuation `--ink-faint`:

```json
{
  "objective": "bleed_and_withdraw",
  "acceptable_own_losses": 0.35,
  "required_enemy_losses": 0.90,
  "abort_if": { "general_dies": true }
}
```

Body:

> It never selects an action. It declares a target result, and aggression is computed from that — which also makes the intent checkable after the fact.

**Cell 3.** Title: `Nobody writes down what a good move is`

Visual: four rows, each a `--panel-2` box with a mono identifier in `--accent` on the left and a mono description in `--ink-faint` right-aligned:

| Left | Right |
|------|-------|
| `dump_fac_score` | faction strength |
| `UnitHasRouted` | battle event |
| `I_BattleEnd` | outcome signal |
| `set_ranking_interval` | faction rank |

Body:

> No hand-tuned evaluation function. Rome computes scores, casualties and rankings itself — the agent's opinions are hypotheses, the outcome log is the judge.

### 8.5 Section 5 — Components

Eyebrow `WHAT IS BEING BUILT`. h2: `The component map`. Wide container.

One lead paragraph:

> Three processes on the Windows box and an engine on a second machine. The split exists so a stalled agent or a hung interface can never leave a key held down.

Then a `{% for group in site.data.components %}` loop. Each group renders a header row — the group name in `--ink` 0.95rem, the subtitle in `--ink-dim` 0.86rem — then its items as rows in a two-column grid: name (`--ink`, 0.92rem) plus `does` (`--ink-dim`, 0.88rem) on the left, and on the right a mono `PHASE {{ item.phase }}` label plus a status pill.

**Component status is derived, never stored.** Look up the phase in `phases.yml` and reuse its status:

```liquid
{% assign ph = site.data.phases.phases | where: "id", item.phase | first %}
```

So a component's pill is the pill of the phase that builds it. Adding a `status` field to `components.yml` is a bug.

Below the loop, embed the overlay mockup still:

```html
<figure>
  <img src="{{ '/assets/img/overlay-screen.png' | relative_url }}" loading="lazy"
       width="1440" height="810"
       alt="The overlay in use over a Rome Remastered battle: an edge glow, a virtual keyboard, a cursor with an intent marker, and a translucent AO cycle window">
  <figcaption>What the screen looks like while it plays. <a href="…">The live mockup</a>.</figcaption>
</figure>
```

`figcaption` is 0.82rem `--ink-faint`. The mockup link href is an open item — see section 15.

### 8.6 Section 6 — Build tracker

Eyebrow `BUILD TRACKER`. h2: `How far along it is`. Wide container. This is the section the site exists for.

**Summary line**, above the stepper, mono 0.86rem, separated by `&middot;` in `--rule`, all three numbers computed from `phases.yml`:

`{{ done }} of {{ total }} complete · {{ blocked_count }} blocked · phase {{ current_phase }} next`

The blocked count renders in `--blocked` when it is above zero. The final clause reads `phase N next` when the current phase is `not_started`, and `phase N in progress` when it is `in_progress`.

**The stepper.** `{% for phase in site.data.phases.phases %}`, a two-column grid, 64px number column plus body.

Number column: the id zero-padded to two digits (`00`, `01`, … `07`) in 1.5rem mono `--ink-faint`, then a 1px `--rule` vertical connector filling the remaining height. The connector is hidden on the last row.

Body:

- h3 = phase name, with the status pill inline beside it
- summary paragraph, `--ink-dim`, 0.92rem, `max-width:60ch`
- the accept block: `--panel` background, `border-left:2px solid var(--accent-deep)`, a mono `ACCEPT` label in `--accent`, and the acceptance text **verbatim from the data file**
- if `blocked_by` is set: a `--blocked` note reading `Blocked on <a href="#q-{{ blocked_by }}">the question's text</a> — open decision, not yet made.` The anchor targets the matching question in section 11.

**Status pill classes** map one-to-one to the four status values. Pill colours:

| Status | Text | Background | Border |
|--------|------|-----------|--------|
| `not_started` | `--not-started` | `rgba(93,106,114,0.14)` | `rgba(93,106,114,0.4)` |
| `in_progress` | `--progress` | `rgba(232,163,61,0.12)` | `rgba(232,163,61,0.45)` |
| `done` | `--done` | `rgba(127,192,138,0.12)` | `rgba(127,192,138,0.45)` |
| `blocked` | `--blocked` | `rgba(224,104,95,0.12)` | `rgba(224,104,95,0.45)` |

Pill label is the status with underscores replaced by spaces, uppercased, via Liquid — not a lookup table of hand-written labels.

On a blocked phase, the accept block's left border and `ACCEPT` label both switch to `--blocked`, and the phase number renders in `--blocked`.

**Acceptance tests display in full, not behind a disclosure.** They are the most interesting content on the page.

### 8.7 Section 7 — The rules

Eyebrow `THE RULES IT PLAYS BY`. h2: `Enforced in code, not by good intentions`.

A two-column table. Headers `RULE` and `WHAT IT MEANS` in mono `--ink-faint`. First column `--ink` 500 weight, `white-space:nowrap`. Rows separated by `--rule-soft`, last row no border. Four rows, verbatim:

| Fog of war | It sees what a player sees. Every belief carries an age and a confidence that decays. |
| No cheats, ever | `add_money`, `auto_win`, `force_battle_victory` and the rest sit in a hard-blocked set. A run that touches them is tainted and marked. |
| Declares intent | Every action is declared before it executes. No approval gate, nothing waits — but the record exists. |
| Single player only | Automating multiplayer is cheating other people, which is a different thing entirely. |

Below the table, an edge note — `--panel`, 1px `--rule`, 4px radius, 16px 18px padding:

> **One advantage it does take, on purpose:** it freezes and micros every unit on every tick, faster than any human. That's a deliberate mechanical choice, not an oversight — and the tick rate stays a configurable dial.

Lead with the constraints. Do not add a capability list here.

### 8.8 Section 8 — The hard part

Eyebrow `THE HARD PART`. h2: `Windows will lie to you`.

Lead paragraph:

> The interesting engineering here is not the model. It is that the platform reports success for things that did not happen. `SendInput` blocked by UIPI returns success and does nothing, and Microsoft document that neither the return value nor `GetLastError` will tell you.

Then a list of seven failures. Each row: a mono name in `--ink`, and the symptom in `--ink-dim` 0.88rem. Rows separated by `--rule-soft`. No panels, no icons, no severity colours — these are not statuses.

| Name | Symptom |
|------|---------|
| `SendInput` under UIPI | Reports success. Nothing happens. The API can never tell you which. |
| An overlay that is not click-through | Synthetic clicks land on the overlay instead of the game. Identical symptom. |
| An overlay that activates | It takes foreground and receives the input meant for the game. Identical symptom again. |
| Acting in the wrong game state | Clicks during a loading screen do nothing, or queue and fire unpredictably. Map orders with a modal open land on the modal. |
| `WDA_EXCLUDEFROMCAPTURE` before build 19041 | Degrades silently to `WDA_MONITOR`, which renders the window blank rather than absent. A black rectangle inside the frame the model reasons over. |
| `SendInput` and held keys | It does not reset keyboard state. Keys already held interfere with the events it generates. |
| AO's answer cache | `AGENTIC_ANSWER_CACHE` short-circuits a repeated goal to a cached answer. The same question in a different board state returns the old reply. |

Closing paragraph:

> Which is why every action in this system is a closed loop: declare, execute, verify by observation, retry. Not because it is elegant, but because the alternative is a system that appears to work and does not.

Second image goes here, right-aligned or full width inside the prose container:

```html
<img src="{{ '/assets/img/annotation-1920.jpg' | relative_url }}" loading="lazy"
     width="1920" height="1080"
     alt="A battle line seen from a low wide angle, with flat cyan annotation boxes labelling each formation">
```

Its flatter annotation style is deliberately different from the hero, so the page has two registers rather than one repeated.

### 8.9 Section 9 — Built on Agentic Orchestration

`id="reference"`. Eyebrow `BUILT ON`. h2: `Agentic Orchestration`.

Three cards in a row, single column below 820px. Each: the repo name in mono `--accent`, one line of role in `--ink-dim` 0.88rem, and the whole card is the link. `--panel` background, 1px `--rule`, 4px radius, hover raises the border to `--accent-deep`.

| Repo | Role |
|------|------|
| `agentic-orchestration` | The engine. Model-agnostic catalogs, dynamic planning, RAG sources, agent skills. Runs on a second box beside the model. |
| `agentic-orchestration-reach` | The client SDK. Session overlays register ephemeral agents for a match; a reverse tunnel exposes local game state without opening a port. |
| `FeralInteractive/romeremastered` | Feral's official modding documentation, which publishes the combat and campaign formulae the deterministic predictors are built from. |

URLs come from `site.ao_url`, `site.reach_url`, `site.feral_url`.

### 8.10 Section 10 — The design set

Eyebrow `THE DESIGN SET`. h2: `Ten documents, no code yet`.

Lead:

> The design is the actual asset right now. Every decision below is made, recorded and justified, and the build brief exists — what does not exist is a line of implementation.

Then `{% for doc in site.data.docs %}` as a two-column list: filename in mono `--accent`, description in `--ink-dim`. Each filename links to the file in the repo: `{{ site.repo_url }}/blob/main/{{ doc.name }}`. Rows separated by `--rule-soft`.

### 8.11 Section 11 — Open questions

Eyebrow `OPEN QUESTIONS`. h2: `What is deliberately unmade`.

Lead:

> These are not oversights. Each one is a decision that has not been made yet, and each one blocks something specific.

`{% for q in site.data.questions %}`. Each entry carries `id="q-{{ q.id }}"` so the tracker can link to it. Renders: the question in `--ink` 0.98rem, the detail in `--ink-dim` 0.88rem, and a mono `BLOCKS {{ q.blocks | upcase }}` label in `--blocked`.

The page ends on candour, not a call to action. Do not add a contact form, a newsletter, a "star the repo" button, or a "get in touch" line.

### 8.12 Footer

`id="foot"`. A thin rule, then two lines:

- Repo links row: the three GitHub URLs, mono 0.8rem, `--ink-dim`, underlined in `--rule`
- Legal line, 0.8rem `--ink-faint`:

> Apache-2.0, same as the engine. Not affiliated with Creative Assembly, Feral Interactive or SEGA.

No copyright year, no "built with" credit, no social icons.

---

## 9. Assets

Source files are in the design bundle under `images/hero/`. Copy and rename:

| Source | Destination | Notes |
|--------|-------------|-------|
| `aerial-dust-hero-2560x1097.jpg` | `assets/img/hero-2560.jpg` | Hero, 2560×1097 |
| `aerial-dust-hero-2560x1097.jpg` | `assets/img/hero-1280.jpg` | **Downscale to 1280×549** for the srcset. Do not ship the 2560 file twice |
| `aerial-dust-og-1200x630.jpg` | `assets/img/og-1200x630.jpg` | Social card, 1200×630 |
| `wide-landscape-16x9-1920x1080.jpg` | `assets/img/annotation-1920.jpg` | Section 8 |
| `overlay-screen.png` | `assets/img/overlay-screen.png` | Section 5 |

Every `<img>` carries explicit `width` and `height` attributes matching the real pixel dimensions, so nothing shifts as images load. Every image except the hero carries `loading="lazy"`. Every image carries a real `alt` describing what is in it — the alt text for the hero and the two others is given in section 8.

`assets/img/favicon.svg`, exactly this:

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
  <rect width="32" height="32" fill="#0c1012"/>
  <rect x="15" y="4" width="2" height="24" fill="#232c31"/>
  <rect x="15" y="4" width="2" height="9" fill="#5fd0e0"/>
  <circle cx="16" cy="13" r="3.5" fill="#5fd0e0"/>
</svg>
```

It is the rail glyph. Do not substitute an emoji, a letter, or a generated icon.

### 9.1 Head

`_layouts/default.html` contains, in this order: charset, viewport, title, description, canonical, the Open Graph and Twitter blocks, the favicon link, the font links, then the stylesheet. `rail.js` loads with `defer` at the end of `<body>`.

```html
<meta property="og:type" content="website">
<meta property="og:title" content="{{ site.title }}">
<meta property="og:description" content="{{ site.tagline }}">
<meta property="og:url" content="{{ page.url | absolute_url }}">
<meta property="og:image" content="{{ '/assets/img/og-1200x630.jpg' | absolute_url }}">
<meta name="twitter:card" content="summary_large_image">
```

`og:image` uses `absolute_url`, not `relative_url`. A relative OG image does not render on any platform, and it is a silent failure — the card just looks empty.

No `jekyll-seo-tag`, no generated sitemap, no `robots.txt`, no analytics of any kind.

---

## 10. Accessibility

Not optional, and all of it is cheap here.

- The rail nodes are `<a>` elements with real hrefs and visible labels on `:focus-visible`. Tabbing through them must be usable with no mouse.
- Global focus style: `outline:2px solid var(--accent); outline-offset:3px`. Never `outline:none` without a replacement.
- `html { scroll-behavior: smooth }`, but wrapped in `@media (prefers-reduced-motion: no-preference)`.
- A `@media (prefers-reduced-motion: reduce)` block collapses all transition and animation durations to `0.01ms`.
- One `<h1>` on the page, in the hero. Every section leads with an `<h2>`. Card and phase titles are `<h3>`. Do not skip levels for visual reasons.
- The rail is `<nav aria-label="Section progress">`.
- Contrast: `--ink-dim` on `--ground` is the lightest text used for real content. Do not introduce anything dimmer for body copy. `--ink-faint` is for labels only.
- The decorative divider spans in the wordmark and summary line carry `aria-hidden="true"`.

---

## 11. Performance budget

| Item | Budget |
|------|--------|
| `main.css` | ≤ 20 KB unminified |
| `rail.js` | ≤ 3 KB unminified |
| Hero image | ≤ 750 KB at 2560, ≤ 250 KB at 1280 |
| Total first load | ≤ 1.6 MB |
| Render-blocking requests | The font stylesheet and `main.css` only |

Do not inline the stylesheet, do not base64 images into the CSS, do not add a service worker or a preloader.

---

## 12. Build order

Each step has a check. Do not start one before the previous passes.

### Step 0. Skeleton and Pages build
`_config.yml`, `Gemfile`, `.gitignore`, `_layouts/default.html`, an `index.html` that renders nothing but the tokens.
**Accept:** the site builds on GitHub Pages, resolves at the project URL, and the stylesheet loads through `relative_url` — verified on the live Pages URL, not just locally.

### Step 1. Tokens, type, shell
Full token block, font links, the layout shell and the three breakpoints.
**Accept:** all three faces render (not a fallback), the page is `--ground` from edge to edge, and no horizontal scroll appears at 390px, 820px or 1440px.

### Step 2. The rail
`rail.html` and `rail.js`, all eight nodes, fill, cap, active detection, mobile collapse.
**Accept:** fill reaches 0% at the top and 100% at the bottom; each node activates as its section crosses centre; tabbing reveals labels; below 900px it is a top bar with no nodes; with reduced motion set, nothing animates.

### Step 3. Data-driven sections
`phases.yml`, `components.yml`, `questions.yml`, `docs.yml` plus sections 5, 6, 10, 11 and the hero chip.
**Accept:** change `status: not_started` to `in_progress` on phase 0 in `phases.yml` alone, and the hero chip text, the summary line, the phase pill, the phase-0 component pills and the rail cap all change. Then `grep -ri "not_started\|not started" _includes/ index.html` returns only class names and Liquid expressions, never a rendered label.

### Step 4. Narrative sections
Sections 1, 2, 3, 4, 7, 8, 9 and the footer, with copy verbatim from section 8 of this document.
**Accept:** every string on the page appears either in this handoff or in a `_data` file. A diff of rendered text against section 8 shows no additions.

### Step 5. Assets, head, polish
Images at the right dimensions, favicon, OG tags, alt text.
**Accept:** the OG card previews correctly with an absolute image URL; no image causes layout shift; the page loads inside the budget in section 11.

### Step 6. Verification pass
**Accept:** keyboard-only navigation reaches every link and rail node; axe or the browser's accessibility audit reports no violations; the page renders correctly at 390px, 768px, 1440px and 2560px; and no console errors or 404s appear on the live Pages URL.

---

## 13. Maintaining it

When a phase moves, edit one line in `_data/phases.yml`. The hero chip, the rail cap, the summary line, the stepper and the component pills all follow.

When a question is answered, delete it from `_data/questions.yml` and clear the `blocked_by` on any phase pointing at it.

That is the entire maintenance surface. **If a status update ever requires touching a file in `_includes/`, the implementation is wrong.**

---

## 14. Do not build

- A second page, a blog, a docs section, or a navigation menu
- A light theme or a theme toggle
- A hamburger menu or any mobile navigation
- A hero at `100vh`
- A changelog, a roadmap with dates, or an ETA of any kind
- A contact form, newsletter signup, "star this repo" button, or social share buttons
- Analytics, cookie banners, consent dialogs, or any third-party script
- Scroll-triggered fade-ins, parallax, counters that count up, typewriter effects, or particle backgrounds
- A reading-progress percentage or reading-time estimate
- Emoji anywhere in the interface
- Rounded corners on everything, drop shadows on cards, or an accent bar on every panel
- Tailwind, Bootstrap, React, Alpine, jQuery, GSAP, AOS, or any other dependency
- A `package.json`, a bundler config, or a GitHub Actions workflow
- Any status value outside the four in section 7.1
- Any copy not present in this document or in `_data`

---

## 15. Open decisions. Ask, do not decide

| # | Question | Default this handoff pins |
|---|----------|---------------------------|
| 1 | **Rail behaviour.** Option A, the rail is scroll position and navigation with a static build-count cap. Option B, the rail's nodes become the seven phases as you scroll into the tracker | **A is specified above and is what to build.** Do not implement B unless told |
| 2 | **Where the live overlay mockup is hosted**, for the link in section 5's figcaption. Until this is answered, render the caption without a link | Unresolved. Do not invent a URL |
| 3 | **Domain.** `zlatko-lakisic.github.io/comstar-game-ai` or a custom domain, which would change `url`, `baseurl` and add a `CNAME` | Project path, as configured in 2.1 |
| 4 | **Repo name**, if the site lives somewhere other than a repo called `comstar-game-ai` | `comstar-game-ai` |

If you need an answer to any of these, stop and ask. Do not pick a sensible default and continue.

---

## 16. Reference files

| File | Contains |
|------|----------|
| `site-preview-reference.html` | Working reference implementation. Final tokens, type, rail and sections 1, 2, 4, 6, 7. Its CSS is the source of truth for anything this document does not override |
| `website-outline.md` | The site plan this handoff implements |
| `cursor-handoff.md` | The system build brief. Source of every phase name and acceptance test |
| `decisions.md` | Where the copy's claims come from, if you need to check one |
| `README.md` | The repo's own front page. Its voice is the site's voice |

Where this handoff and a reference document disagree, **this file wins**.
