# Comstar Game AI: design and build handoff

An AI opponent for Total War: Rome Remastered. Architecture and implementation brief.

## Start here

**`cursor-handoff.md`** is the implementation brief. Read it completely before writing code.
It is self contained, and where it disagrees with anything in `design/`, it wins.

## Contents

| Path | What |
|------|------|
| `cursor-handoff.md` | The build brief: constraints, architecture, build order, open questions |
| `working-agreement.md` | Roles, the decision rule, the label key for D / C / B numbering |
| `decisions.md` | D1 to D12 with consequences C1 to C15 and the risk register |
| `design/smart-player-architecture.md` | Generic smart player design, directive contract history |
| `design/rtw-remastered-integration.md` | Observation channels, actuation tiers, game state machine, fair play |
| `design/host-app-architecture.md` | Capture, input injection, process split, safety layer |
| `design/host-overlay-ui.md` | The on screen operator overlay |
| `design/reach-overlay-design.md` | AO session overlay, run modes, connection config, call patterns |
| `design/bottlenecks.md` | The eight system constraints with numbers and reasoning |
| `design/agentic-orchestration-platform-context.md` | AO engine and AO Reach SDK reference |
| `hero-image-prompt.md` | Gemini prompt for the battlefield hero still |
| `images/hero.png` | Generated hero still (warm field, thin cyan annotation) |
| `images/overlay-mockup.html` | Live mockup of the overlay, animated |
| `images/overlay-mockup.png` | Full page still of the mockup |
| `images/overlay-screen.png` | The screen on its own |

## The short version

Two tier reasoning, no tree search. A local model on a separate box supplies intent through
AO Reach; a reactive layer with deterministic predictors built from the game's published
formulae does the playing. The agent plays fogged, declares what it intends before acting,
never uses cheat commands, and learns from its own play, the native AI factions and the human.

Everything that reports success and does nothing is listed in section 3 of the handoff.
That section is the whole ballgame.
