# Comstar Game AI: build handoff

**For an AI coding agent. Read this file completely before writing anything.**

This is the implementation brief for a system designed across a long architecture session. Every design decision here has already been made and justified. Your job is to build it, not to redesign it.

Written 2026-09-01.

---

## 0. Rules of engagement

1. **Open questions are settled.** Section 11 lists decisions resolved 2026-09-01. If a new ambiguity appears, stop and ask.
2. **Do not redesign settled decisions.** Sections 2 and 3 contain constraints that look arbitrary and are not. Each one exists because of a specific documented failure mode.
3. **Verify, never assume.** The dominant failure mode in this system is an operation that reports success and does nothing. Section 3 lists every known instance. Every one needs an explicit runtime check.
4. **Single player only.** This automates a single player game. Nothing here touches multiplayer.
5. **No process injection, no memory reading.** The entire design deliberately stays on the scripting, console and synthetic input path. Do not reach for DLL injection, DirectX hooking, or reading game memory even where it would be faster.

---

## 1. What is being built

An AI that plays **Total War: Rome Remastered** autonomously as an opponent faction, on a Windows machine, using:

- The game's own scripting and console interfaces for observation
- Synthetic keyboard and mouse for actuation
- A local LLM, reached through **AO Reach** to an **Agentic Orchestration** engine, for strategic deliberation
- Deterministic predictive models built from the game's published combat formulae
- A continuously updated corpus of decisions and outcomes

The agent plays fogged, meaning it sees only what a human player could see. It declares what it intends before it acts. It never uses cheat commands.

### Machines

| Host | Role |
|------|------|
| Windows box | Rome Remastered, the host app, the overlay |
| `ada` server, same LAN | AO engine and the model. NVIDIA RTX 4000 Ada Generation, 20 GB, 360 GB/s |

### Repositories to read before starting

| Repo | Why |
|------|-----|
| `github.com/zlatko-lakisic/agentic-orchestration` | The engine. Read `docs/rag-catalog`, `docs/agent-skills`, `docs/sessions-learning-kb`, `agentic-orchestration-tool/README.md` |
| `github.com/zlatko-lakisic/agentic-orchestration-reach` | The client SDK. Read `python/ao_reach/` in full, especially `session_bridge.py`, `overlay_packer.py`, `connection_config.py` |
| `github.com/FeralInteractive/romeremastered` | Official modding docs. `documentation/feature_guides/scripts/` and `Battle_and_Campaign_Formulae.md` are load bearing |

---

## 2. Hard preconditions

The app must check all of these at startup and refuse to run if any fails. Do not make them warnings.

| Precondition | Why |
|--------------|-----|
| Game is in **borderless windowed**, never exclusive fullscreen | Exclusive fullscreen bypasses DWM composition, so capture is unreliable and intermittent |
| Host app and game run at the **same integrity level** | `SendInput` cannot inject into a higher integrity process, and the failure is silent |
| Capture exclusion self test passes | Render a known pattern into every overlay surface, capture through the real path, assert absent |
| Overlay click through self test passes | Synthesise a click where the overlay covers, confirm the game received it |
| Overlay non activation self test passes | After showing the overlay, assert `GetForegroundWindow` is still the game |
| Game version matches the pinned version | UI layout changes across patches break actuation |

---

## 3. Known silent failures. These are the whole ballgame

Every item here reports success and does nothing. If you build this system without handling them, it will appear to work and will not.

### 3.1 `SendInput` under UIPI

Microsoft document that when UIPI blocks `SendInput`, **neither the return value nor `GetLastError` indicates it**. You can never learn from the API whether an action landed.

**Required:** every action is a closed loop. Declare intent, execute, verify by observation, retry or escalate. Never fire and forget.

### 3.2 An overlay that is not click through

If the overlay lacks `WS_EX_LAYERED | WS_EX_TRANSPARENT`, synthetic clicks land on the overlay. `SendInput` reports success. The game does nothing. Identical symptom to 3.1.

### 3.3 An overlay that activates

If the overlay lacks `WS_EX_NOACTIVATE`, it takes foreground and receives input meant for the game. Identical symptom again.

### 3.4 Acting in the wrong game state

Clicks during a loading screen do nothing or queue and fire unpredictably. Map orders with a modal scroll open land on the scroll. **Every action must assert its expected game state before executing.**

### 3.5 `WDA_EXCLUDEFROMCAPTURE` on Windows before 10.0.19041

It degrades silently to `WDA_MONITOR`, which renders the window **blank** in captures rather than absent. A black rectangle over the game corrupts the frame the model reasons over, without looking obviously wrong.

### 3.6 `SendInput` and held keys

It does not reset keyboard state. Keys already held when it is called interfere with the events it generates. Check `GetAsyncKeyState` and normalise before every sequence.

### 3.7 AO's answer cache

`AGENTIC_ANSWER_CACHE` short circuits a repeated goal to a cached answer. **Turn it off.** The same question text in a different board state must never return a cached reply.

### 3.8 Reach allowlist asymmetry

Since Reach 0.13.0, empty `allowedMcpProviderIds` and `allowedSkillIds` mean **overlay entries only**, which is what is wanted. But an empty `allowedAgentProviderIds` means **unrestricted**. List the agent ids explicitly.

### 3.9 `OverlayPacker` rewrites what you give it

It prefixes every agent and skill id with `client.`, and for `type: ollama` it drops `ollama_host` and forces `selfcontained: false`. Skills listed on an agent are **concatenated into that agent's `backstory` at pack time**, so skill text costs prefill on every call and new skill content only goes live on a re-pack plus `refresh_overlay`.

---

## 4. Architecture

### 4.1 Processes

```
Windows box
├── Process A  Game I/O          owns the kill switch, never allowed to stall
│   ├── WGC window capture, ring buffer, frame selection
│   ├── SendInput actuator, diff based order computation
│   ├── RomeShell console channel
│   ├── log tailers
│   ├── game state machine, window and focus watchdog
│   ├── control state machine: take over / hand back / kill
│   └── intent record writer
│
├── Process B  Agent runtime     allowed to stall
│   ├── belief store
│   ├── deterministic predictors
│   ├── view compositor
│   └── Reach client -> AO on ada
│
└── Process C  Overlay UI        allowed to crash
    └── observes a one way event stream from A and B

ada server
├── AO engine (orchestration.serve, port 8765, mTLS)
└── the model
```

**The split exists so a stalled agent or a hung UI can never leave keys held down.** Process A must always be able to release input and honour the kill switch.

### 4.2 Two tier reasoning, no tree search

Decision D10 removed search. What remains:

- **Deliberation**, the LLM via AO, slow, produces multi step intent
- **Reactive**, fast, single step, consults deterministic predictors

The predictors are one step only. Error never compounds, so they only have to be accurate one step ahead.

### 4.3 Deliberation is never in the critical path

A move is never blocked on AO. Timeouts, `ReachRunError` and malformed responses all resolve to a **neutral directive** and play continues.

---

## 5. Observation

Four channels, ranked. Never make vision the primary state source.

| Channel | What | Notes |
|---------|------|-------|
| Background script telemetry | Campaign state, state machine transitions | `descr_strat.txt` declares the script. `for_each` plus `script_log` writes to `/VFS/Local/Rome/logs/scripting_log.txt`. Full dump every 5 to 10 turns, deltas per turn, because the script interpreter is slow |
| Engine logs | `message_log.txt`, `campaign_ai_log.txt` | Launch option `enable_logging`. `campaign_ai_log.txt` is **privileged**, see 8.2 |
| RomeShell console queries | `output_unit_positions <file>` (battle), `list_characters`, `list_units`, `show_cursorstat` | `output_unit_positions` writes structured battle geometry to a file |
| Vision | Terrain, formations, UI with no console equivalent, drift detection | Composed views only, see 7 |

### 5.1 Belief contract

The agent plays fogged, so it never holds world state. Every entity in the belief store carries:

- **provenance**: which channel supplied it
- **age**: when last directly observed
- **confidence**: decays, and differently per attribute
- **existence status**: observed present, believed present, believed destroyed, never seen

An enemy army is a last known position, an elapsed time, an implied movement range, and a possibly stale composition estimate.

### 5.2 Game state machine

Required by 3.4. States and behaviour:

| State | Agent |
|-------|-------|
| Launcher, loading, main menu | Idle. Takeover not offered |
| Campaign map, no modal | Campaign loop |
| Campaign modal open | Must not issue map orders |
| Pre battle scroll | Decide fight / auto resolve / withdraw, declare battle intent |
| Battle deployment | **Untimed.** Full reasoning mode affordable here and nowhere else in a battle |
| Battle in progress | Freeze tick loop |
| Post battle scroll | Harvest outcomes, write after action record |
| Campaign end | Post mortem, stand down |

Detection, in order of preference: background script events (`NewTurnStart`, `I_BattleEndPending`, `I_BattleEnd`, `I_BattleFinished`), console command availability by mode, then vision as cross check.

---

## 6. Actuation

Prefer text over pixels. Every console command replaces a class of pixel bugs.

| Tier | Mechanism |
|------|-----------|
| 1 | RomeShell console commands. `move_character <name> <x>,<y>` is exact where clicking is not |
| 2 | Turn sequence control: `halt_ai`, `run_ai`, `ai_turn_speed` |
| 3 | Synthetic mouse and keyboard for recruitment, construction, end turn, battle orders |

### 6.1 Fair play boundary. Enforce in code, not by convention

Split the command surface three ways and make the cheat set a flag that taints any run using it:

| Class | Commands |
|-------|----------|
| **Allowed at runtime** | Observation of what a player could see, movement and orders a player could issue, turn sequence control |
| **Evaluation only** | `toggle_fow`, `toggle_perfect_spy`. Ground truth for scoring belief quality. **Never fed back to the agent** |
| **Never** | `add_money`, `auto_win`, `force_battle_victory`, `force_autoresolve_outcome`, `capture_settlement`, `process_cq`, `create_unit`, `give_trait`, and every other cheat |

### 6.2 Going fast means acting less

Battle tick rate is unthrottled by decision. The ceiling is actuation, not decision: roughly 100 to 300 ms per unit order, so twenty units is 2 to 6 seconds per tick before any thinking.

1. **Diff based actuation.** Compute desired state, diff against current, issue only the delta. Removes an estimated 80 to 90 percent of input work. Build this first, not as an optimisation later.
2. **Batch through control groups** rather than per unit sequences.
3. Make the tick rate a config value, never a constant.

### 6.3 Intent record

Required, per decision D1. Every action: `declare intent -> execute -> observe outcome`. No approval gate, nothing waits.

Log `{question_id, ply_or_tick, state_hash, intent, action, expected_effect, observed_effect, latency_ms}`.

This is what separates a bad observation from a stale belief from bad reasoning from a silent actuation failure. Without it those four produce one indistinguishable symptom.

### 6.4 Verification

Tiered, because per action screenshots would consume the whole vision budget:

| Tier | When |
|------|------|
| Structured check, log or console | Default, every batch |
| Vision, one composed view | Only when the structured check disagrees |
| Full re-observation | Only after a failed retry |

Optimistic execution with periodic reconciliation. Most actions succeed.

---

## 7. Capture and the overlay

### 7.1 Capture

**WGC window capture of the game window is primary.** Not Desktop Duplication. The reason is not the overlay: Desktop Duplication captures the whole monitor, so Windows toasts, the Steam overlay and Discord popups land in frames, and none can be excluded by display affinity because they are not our windows.

`WDA_EXCLUDEFROMCAPTURE` (`0x00000011`) on every overlay surface as a second line. Top level windows only, owned by the calling process.

Keep a rolling ring buffer of recent frames so the selector can look **backwards** after an event, rather than streaming forwards.

### 7.2 View compositor, not screenshot sender

Reach caps a turn at 16 images, 4 MiB each, 20 MiB total. A raw 1440p PNG is 3 to 8 MiB, so two exhaust the budget.

Compose each view from the pieces that carry decision relevant information: contested area at usable zoom, minimap, relevant unit cards, current selection. Target roughly 1280x720 JPEG q80, about 150 to 300 KiB, four to six views per deliberation.

### 7.3 Overlay surfaces

Four, all click through and non activating, all excluded from capture:

1. **Edge glow** sized to the game window, colour encoding state: deliberating, acting, suspended, fault, idle. A text chip names the state so the colour need not be memorised.
2. **Virtual keyboard**, only the keys the agent uses, fades in on press and out after idle. Held modifiers stay lit, taps flash.
3. **Cursor indicator**, ring plus short trail, different colour for synthetic versus human. A dashed leash and hollow marker appear at the destination **before** the cursor travels there.
4. **AO cycle window**, top right, translucent. Request, live status from `ReachRunStatus` including queue position and phase, directive with latency, the intent it produced, and the verification result.

A visual mockup of all four exists and should be treated as the reference.

### 7.4 Control transitions

Three, not one. The click through overlay cannot host a button, so all three are hotkeys handled in Process A.

| Transition | Behaviour |
|------------|-----------|
| Take over | Offered only in a playable state. Agent begins acting |
| Hand back | Finish current action cleanly, release, go idle |
| Kill | Release everything immediately, mid action if needed |

Kill also fires on the dead man's timer, on human mouse movement, and on the game losing foreground. All held keys and buttons release on **every** exit path including crash.

---

## 8. AO integration

### 8.1 Session overlay

Layout on disk:

```
overlay/
├── agent_providers/
│   ├── battle_director.yaml
│   ├── campaign_director.yaml
│   ├── opponent_modeler.yaml
│   ├── narrator.yaml
│   ├── consolidator.yaml
│   ├── doctrine_ingestor.yaml
│   └── post_mortem.yaml
└── agent_skills/          (small stable core only, see 3.9)
```

All seven point at the same model on `ada`.

**Run mode.** The play loop uses `direct_agent`, not `chat` and not dynamic planning. The task is one typed transformation with a known shape; routing it through the planner costs a planner call plus a call per step, turning 6 to 9 seconds into 30 to 90.

| Agent | Mode | Priority | Timeout |
|-------|------|----------|---------|
| `battle_director` | `direct_agent` | high | 20s |
| `campaign_director` | `direct_agent` | high | 90s |
| `opponent_modeler` | `direct_agent` | default | 120s |
| `narrator` | `direct_agent` | realtime | 15s |
| `consolidator` | `chat`, `dynamic` | default | none |
| `doctrine_ingestor` | `chat`, `dynamic` | default | none |
| `post_mortem` | `chat`, `dynamic-iterative` | default | none |

**Two prompt modes on one model.** Tactical mode at battle events: constrained output, no visible reasoning, 100 to 150 tokens, target 6 to 9 seconds. Strategic mode at campaign turn boundaries and battle deployment: reasoning allowed, 800 plus tokens, half a minute is fine.

**Connection config.** `app_id: comstar-game-ai`, mTLS to the engine on `ada`, `ttl_seconds: 3600` with refresh, `dynamic_planning: False`, `default_run_mode: dynamic`, agent allowlist listing all seven ids explicitly, MCP and skill allowlists empty, `session_env` empty, `deploy_to_ao_sandbox: False`.

Every call passes an explicit `question_id`. `cancel` requires a tagged run.

**One tunnel MCP: `client.game_query`**, read only. AO never actuates. There is deliberately no act tool; the directive returns as a run result and Process A decides what to do with it.

### 8.2 Deliberation triggers

Battle: **event driven with a floor.** Events are first contact, a unit routing, a flank exposed, reserves needed, general down, unexpected reinforcement. Floor is 30 to 60 seconds of battle time, generous because a tactical call costs 6 to 9 seconds.

Campaign: at the turn boundary. Deliberation runs during the human's turn or under `halt_ai`, never blocking.

### 8.3 The directive contract

```json
{
  "intent": {
    "objective": "annihilate | win_cheaply | hold | bleed_and_withdraw | capture_general | take_settlement | survive",
    "acceptable_own_losses": 0.35,
    "required_enemy_losses": 0.90,
    "hold_for_seconds": null,
    "preserve": ["unit ids that must survive"],
    "abort_if": { "own_losses_exceed": 0.60, "general_dies": true }
  },
  "horizon": "short | normal | long",
  "risk_posture": -1.0,
  "focus_actions": [],
  "avoid_actions": [],
  "opponent_read": { "style": "", "predicted_plan": "", "confidence": 0.0 },
  "commentary": "",
  "valid_for_plies": 4
}
```

Rules, and these are the safety model:

- `horizon` sets discount rate, `risk_posture` runs -1 averse to +1 seeking. Neither changes what a good outcome is, only which good outcomes are preferred.
- `focus_actions` add bounded prior weight. `avoid_actions` reduce it, never to zero.
- **The reactive layer never loses access to a legal action.** No filtering by the model.
- `valid_for_plies` expires the directive. Past expiry, neutral.
- Malformed, late or missing means neutral directive, log it, keep playing.

**An intent is a prediction.** Before accepting it, the deterministic layer checks feasibility against a strength estimate and forces a downgrade if the model has declared annihilation against a superior force.

---

## 9. Evaluation and learning

### 9.1 Evaluation is deliberately minimal

No Elo harness, no simulator round robin. Watching it play, plus an optional 20 to 30 game check against the vanilla AI when a number is wanted.

**But keep two logs from day one, because they cannot be reconstructed later:** the intent record (6.3) and the prediction log (every predictor output paired with the observed outcome).

### 9.2 Outcome grounded, never authored

Nobody writes down what a good position is worth. Dynamics are authored from Feral's published formulae. **Values are learned from game measured outcomes.**

Signals the engine computes:

| Signal | Source |
|--------|--------|
| Faction scores | `dump_fac_score`, goes to the debug stream |
| Faction ranking over time | `set_ranking_interval` |
| Region fertility | `dump_fertility` |
| Settlements, treasury, army strength | Script telemetry |
| Battle ended | `I_BattleEnd`, `I_BattleFinished` |
| Unit routed | `UnitHasRouted`, `BattleUnitActionStatus <unit>, routing` |
| Unit strengths over time | `output_unit_positions` sampled |

**Caution:** `dump_fac_score` is Rome's own opinion and the shipped AI is not strong. Confirm faction score correlates with actually winning before trusting it as a target.

### 9.3 Continuous experience learning

Three sources, three trust levels:

| Source | Volume | Strategic quality | Role |
|--------|--------|-------------------|------|
| Own play | Low | Improving | Only source reflecting the current agent |
| Native AI factions | **Very high**, roughly 4,000 faction turns per campaign | Mediocre | Physics teacher, not strategy teacher |
| The human | Low | Good | Demonstration set and style model |

**Valence is relative to expectation, not absolute.** Winning a battle you should have won easily with heavy casualties is a bad outcome. So the learning signal is **prediction error**. Store and weight by surprise: a battle that went as predicted teaches nothing, and filtering by the gap bounds corpus growth without an arbitrary cap.

**Records split into observable and privileged parts.** Only the observable part is retrievable during play. `campaign_ai_log.txt` decisions and fog lifted ground truth are privileged, offline only. **Without this split the AI log is a fog of war exploit wearing a learning hat.**

**Consolidation.** Offline, periodically, read accumulated records and write generalisations into doctrine. Retrieval stores instances and matches on surface similarity, so without an abstraction step you accumulate thousands of instances and retrieve the wrong ones.

**The retrieval key is the hard part.** Similar situation and similar text are not the same thing. Each record needs a structured header the retrieval matches on: numbers ratio, composition classes, terrain, attacking or defending, objective, general quality. Narrative underneath as payload. Use `embedding` or `hybrid` backends, not plain `sqlite-fts`.

### 9.4 Doctrine ingestion

Triage every document three ways:

| Content | Destination | Prompt cost |
|---------|-------------|-------------|
| Rules and tables: counters, terrain modifiers, formation matchups | Structured, consumed by the deterministic layer | **Zero** |
| Doctrine that always applies | Agent skill, injected every call | Small, fixed |
| Situational reference | RAG corpus, retrieved on demand | Variable |

Most of the value is the first bucket. Do not fine tune the model on strategy prose; it teaches the model to talk like a guide, not to play like one.

Every document carries provenance: source, date, **game version** (original, Remastered, patch), **mod** (vanilla or which overhaul), and confidence updated by outcome evidence. Without version and mod the corpus poisons itself, since much Rome strategy writing predates Remastered.

**Doctrine is a prior, not truth.** If the guides say a tactic always works and the outcome log disagrees, the outcome wins.

**Filter exploit tactics.** A meaningful share of Total War writing describes abusing the AI. And note that continuous learning means the agent can now **discover** exploits rather than only read about them, which input filtering cannot prevent. Flag any tactic winning overwhelmingly and cheaply against varied opposition.

---

## 10. Build order

Each phase has an acceptance test. Do not start a phase before the previous one passes.

### Phase 0. Preconditions and capture
Window detection, WGC window capture of the game window, ring buffer, all three self tests from section 2.
**Accept:** self tests pass, frames captured at target rate with the overlay stub absent from them.

### Phase 1. Observation
Background script emitting state and state machine transitions. Log tailers. Console query channel. Belief store with provenance, age, confidence.
**Accept:** campaign state reconstructed externally and matching the screen for 20 consecutive turns. No AI involved.

### Phase 2. Actuation
Console wrapper with the fair play gate. `SendInput` actuator with dwell and hover. Diff based order computation. Verification tiers. Intent record. Game state assertion on every action.
**Accept:** 20 consecutive turns driven end to end, hardcoded, no reasoning, zero desyncs between intended and actual.

### Phase 3. Overlay
Process C, four surfaces, event stream, takeover handshake, three control transitions.
**Accept:** capture exclusion, click through and non activation self tests all pass with the full overlay live. Kill switch releases everything from any state.

### Phase 4. Battle loop
`toggle_game_update` freeze cycle, `output_unit_positions` parse, deployment phase handling, post battle harvest.
**Accept:** a complete battle fought at a fixed tick with no manual intervention, and an after action record written.

### Phase 5. Deterministic predictors
Built from `Battle_and_Campaign_Formulae.md`, `EDU`, `EDB`, `Campaign_Map_Pathfinding.md`. Melee and charge resolution, fatigue and morale, auto resolve estimate, siege duration, economy projection, movement reachability. Prediction log from the first line.
**Accept:** every predictor output paired with an observed outcome in the log.

### Phase 6. AO integration
Reach session overlay, mTLS enrolment, `direct_agent` calls, view compositor, neutral directive fallback, cancellation on stale.
**Accept:** directives influence play, a move is never blocked, every failure path resolves to neutral.

### Phase 7. Learning
After action records, corpus, consolidation.
**Accept:** observable records ingest over mTLS; privileged material never indexed; consolidator stub runs offline.

---

## 11. Settled decisions (2026-09-01)

These were open at handoff time; all are now resolved. See `decisions.md` and the implementation plan for detail.

| # | Question | Decision |
|---|----------|----------|
| 1 | Write path into AO's knowledge base | **Engine HTTP ingest** over mTLS (`POST /api/v1/kb/ingest`, `/upsert`). `deploy_to_ao_sandbox: False` unchanged |
| 2 | Observable vs privileged RAG split | **Ingest-time split** — privileged never indexed. Host pre-injects observable retrieval into `context` until `direct_agent` supports `rag_sources` |
| 3 | Plays | **Adopted** — LLM selects parameterised play; reactive layer executes steps |
| 4 | `campaign_director` + `client.game_query` | **Yes** — tunnel MCP for on-demand pull; composed brief stays primary |
| 5 | Fold `opponent_modeler` | **No** — keep as separate agent |
| 6 | Overlay taste | **Mockup defaults** — compact keyboard bottom-left; modifier/tap styling; dashed leash; 8–10 chat scrollback; expandable directive JSON |

### Unknowns resolved by Phase 0 spikes

| Question | Result |
|----------|--------|
| Console output destinations | See `docs/spikes/preconditions.json` and `scripts/spike_console_output.ps1` |
| Borderless / elevation / version | Documented in `docs/spikes/preconditions.json`; game window optional for dev tests |
| External script signalling | Not available — actuation via SendInput + console |

---

## 12. Do not build

- Any tree search, MCTS or rollout engine. Decision D10 removed it
- An Elo evaluation harness or a round robin. Deliberately shelved
- Any cheat command path that the agent can reach at runtime
- Multiplayer anything
- Process injection, DirectX hooking, memory reading
- An act or command tool exposed to AO. Actuation lives only in Process A
- A full QWERTY virtual keyboard. Only the keys the agent uses
- Fine tuning on strategy prose

---

## 13. Reference documents

The full design lives alongside this file:

| File | Contains |
|------|----------|
| `working-agreement.md` | Roles, decision rule, label key |
| `decisions.md` | D1 to D12 with consequences C1 to C15, and the risk register |
| `smart-player-architecture.md` | The generic three tier design and the directive contract's history |
| `rtw-remastered-integration.md` | Observation channels, actuation tiers, game state machine, fair play, milestones |
| `host-app-architecture.md` | Capture, input injection, process split, safety layer, Reach boundary |
| `host-overlay-ui.md` | The on screen overlay in full |
| `reach-overlay-design.md` | Session overlay, run modes, connection config, call patterns |
| `bottlenecks.md` | The eight constraints with reasoning and numbers |
| `agentic-orchestration-platform-context.md` | AO and AO Reach reference |
| `overlay-mockup.html` | Visual reference for the overlay |

Where this handoff and a reference document disagree, **this file wins**, because it reflects the latest decisions.
