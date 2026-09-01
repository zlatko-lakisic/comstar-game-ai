# Rome Remastered integration

How the Comstar Game AI smart player attaches to Total War: Rome Remastered. Written 2026-09-01 after reading Feral's official modding documentation at [FeralInteractive/romeremastered](https://github.com/FeralInteractive/romeremastered).

Read alongside `smart-player-architecture.md`. This document replaces that document's assumption of a cheap in-game forward model, and section 4 below explains what takes its place.

## 1. What changed from the generic design

Rome is two games sharing a save file, and they need different treatment.

| | Campaign map | Battles |
|---|---|---|
| Time | Turn based | Real time |
| Forward model | None exposed | None exposed |
| Deliberation budget | Minutes | Seconds, and only because the sim can be frozen |
| Actuation | Console text plus UI | Hotkeys plus mouse |

Neither layer gives you `apply(state, action)`. So MCTS over the real game is off the table, and the generic architecture's tactical tier has to be rebuilt. What replaces it is in section 4.

## 2. Observation: four channels, ranked by fidelity

Do not make vision the primary state source. It is slow, expensive, and unreliable for numbers. Use it for what it is uniquely good at, which is the spatial picture and cross checking the model.

**Channel 1, background script telemetry (best fidelity, campaign).** Remastered extends the classic script language so a mod can run a persistent background script, declared at the bottom of `descr_strat.txt`. It has `for_each` to iterate instances within a scope, `if_not` and `while_not`, counters including `declare_persistent_counter` that survive saves, and `script_log` which writes to `/VFS/Local/Rome/logs/scripting_log.txt`. Combined with the `NewTurnStart` event, that is a state exporter: iterate settlements and characters each turn, emit structured lines, tail the log from outside. No memory reading, no OCR, no EULA questions.

**Channel 2, engine logs.** The `enable_logging` launch option writes `/VFS/Local/Rome/logs/message_log.txt` and, valuably, `campaign_ai_log.txt`, which contains the game's own campaign AI decision logging. That is a free window into what the opposing AI is thinking. `verbose_script_logging` adds `scripting_log.txt` and is, per Feral's own warning, very verbose, so gate it behind a debug flag.

**Channel 3, RomeShell console queries.** The console is the tilde key and Feral ship the full command list. The useful readers:

| Command | Availability | What it gives |
|---------|--------------|---------------|
| `output_unit_positions <filename>` | battle | Positions of all units in the battle, written to a file |
| `list_characters <opt:faction>` | campaign | All characters in the world or one faction |
| `list_units <character/settlement>` | campaign | Every unit in an army, with details |
| `show_cursorstat` | both | Cursor position and region id |
| `list_traits`, `list_ancillaries` | campaign | Character detail |

`output_unit_positions` writing to a file is the single most useful thing in the list. Battle geometry arrives as structured data rather than pixels.

**Channel 4, vision.** Screenshots through Reach's image path, capped at 16 images and 20 MiB per turn. Its jobs are terrain and formation gestalt, reading UI state that has no console equivalent, and drift detection, meaning asking whether the screen agrees with the state model the other channels built. The debug overlays help it a lot: `show_battle_paths`, `show_battle_line`, `show_battle_circle`, `show_battle_marker` draw the engine's own intent on screen, which is far easier for a vision model to read than raw terrain.

**Open question to resolve on the machine.** Where do `list_units` and `list_characters` actually print? If they go to the console pane only, that path needs OCR and drops in usefulness. If `enable_logging` captures them, it stays a first class channel. Test this before designing around it.

## 3. Actuation: prefer text over pixels

Every click replaced by a console command deletes a class of bugs. Ranked:

**Tier 1, RomeShell commands.** Precise, text based, no pixel hunting. `move_character <name> <x>,<y>` moves a named character to exact map coordinates. Also available: `diplomatic_stance`, `force_diplomacy`, `diplomacy_mission`, `create_unit`, `create_building`, `process_cq`, `process_rq`, `capture_settlement`, `give_trait`, `season`, `victory`. Note that several of these are cheats and must be off limits for a fair player; see section 6.

**Tier 2, turn sequence control.** `halt_ai <faction>` stops the turn sequence just before a given faction acts, and `run_ai` resumes. `ai_turn_speed` sets a multiplier on AI turn processing. `disable_ai [tac|sub|dip|name]` disables all or part of the AI. These exist for debugging but they are exactly what an external controller needs to get deterministic control over when it is asked to act.

**Tier 3, UI automation.** Recruitment, construction queues, end turn, and battle unit orders have no console equivalent, so they need synthetic mouse and keyboard. The campaign UI is fixed layout, which helps. Calibrate the screen to map transform once per camera pose using `show_cursorstat` rather than guessing at coordinates.

**Tier 4, script side primitives, with a caveat.** The background script has `simulate_mouse_click`, `e_select_unit`, `click_drag_move`, `box_drag_selection`, `unit_group_automate_attack`, `unit_group_automate_defend_position`, `unit_order_move_to_orientation`, and `select_ui_element`. These are far more reliable than raw input synthesis. The catch is that the script is a static file loaded at campaign start and cannot read external input, so an outside agent cannot call them directly. Whether a signalling channel exists, meaning some cheap state change the agent can make that the script can `monitor_event` on and react to, is worth a day of prototyping. If it works, most of tier 3 disappears and the project gets much more robust.

## 4. The forward model, rebuilt

This is what replaces MCTS over the real game.

Feral document the actual combat and campaign math in `Battle_and_Campaign_Formulae.md`: general's bodyguard size, general's battle bonuses, chanting and screeching, hiding, battle difficulty bonuses, experience chevrons, eagle units, fear effects, formation bonuses, campaign difficulty bonuses, plague behaviour, distance to capital penalty, siege turn calculations, and trade calculations. The unit and building data live in `EDU` and `EDB`, both documented.

So build an **abstract simulator** from published formulae plus data files, search in the abstraction, and execute the resulting plan in the real game.

- **Campaign abstraction.** Provinces, income, recruitment pools, movement points, siege timers, army strength as a scalar from EDU stats. This is small enough to roll out thousands of times per turn. Search here is real search.
- **Battle abstraction.** Unit blobs with position, facing, fatigue, morale, and the documented melee and charge terms. Coarse, but enough to answer "does this charge win" and "will this flank break them".

The honest caveat: this is model based planning against an approximation, so it inherits model mismatch. Budget for a calibration loop that compares predicted outcomes against observed ones and fits the residual. Log every prediction with the outcome from day one, even before anything consumes it. That log is what makes the model improve instead of quietly drifting.

## 5. The battle loop, and the trick that makes it work

`toggle_game_update` is a battle console command that freezes the simulation. That converts a real time game into a turn based one, which is what makes LLM speed reasoning viable at all here.

```
battle running
  -> toggle_game_update            freeze
  -> output_unit_positions <file>  structured geometry
  -> screenshot                    spatial and morale context
  -> deliberate                    search on the abstraction, LLM directive if fresh
  -> issue orders                  hotkeys and mouse, or script primitives
  -> toggle_game_update            resume
  -> run for N seconds
  repeat
```

Pick N by how fast the battle line is moving. Two to five seconds during contact, longer while manoeuvring. The tick rate is a difficulty knob in itself, and freezing more often is straightforwardly stronger play, so it belongs in the fairness settings rather than being maximised.

On the campaign side the equivalent is `halt_ai`, which stops the sequence before a faction acts and hands the controller a clean deliberation window with no clock at all.

## 5b. The game state machine

Added 2026-09-01, prompted by the decision that takeover is offered only in a playable state. That requirement generalises: the state machine is not a startup gate, it is a precondition on every action the agent takes.

### Why it is load bearing

Actuation already fails silently under UIPI. Acting in the wrong state produces the same symptom by a different route. Clicks issued during a loading screen do nothing, or queue and fire unpredictably when it finishes. Map orders issued while a diplomacy scroll is open land on the scroll. In both cases `SendInput` reports success and the game does something other than what was intended.

**So every action asserts its expected state before executing.** The actuator refuses a campaign order unless the state says campaign map with no modal. That is cheap, and it closes one of the remaining routes to the hardest failure in this design.

### States, and what the agent does in each

| State | Agent behaviour |
|-------|-----------------|
| Launcher, loading, main menu | Idle. No takeover offered |
| Campaign map, no modal | Campaign loop active |
| Campaign modal open: diplomacy, settlement, event scroll | Must not issue map orders. Either handle the modal deliberately or dismiss it |
| Pre battle scroll | Decide fight, auto resolve or withdraw. **The battle intent from D6 is declared here** |
| Battle deployment | Deployment loop. Untimed, see below |
| Battle in progress | Freeze tick loop, event driven with a floor per B1 |
| Post battle scroll | Harvest outcome measures, write the after action record for D8 |
| Campaign end | Post mortem, stand down |

### Detection signals, layered like observation

Same pattern as section 2: cheap structured signals first, vision as fallback and cross check.

| Signal | Strength | Note |
|--------|----------|------|
| Background script events | Strongest | `NewTurnStart`, `I_BattleEndPending`, `I_BattleEnd`, `I_BattleFinished` write state transitions to `scripting_log.txt`. The game telling you directly |
| Console command availability | Strong | Feral's `console_commands.txt` tags every command `campaign` or `battle`. A command that only exists in one mode is a mode probe. **Open: whether the console reports rejection in a way an external process can read** |
| UI element sets | Medium | `available_ui_elements_strat.txt` and `available_ui_elements_battle.txt` are separate, so the engine distinguishes them. Whether they can be probed externally is unverified |
| Log activity patterns | Weak | Corroborating only |
| Vision classification | Reliable but slow | A screenshot tells you the state trivially. Costs a call, so it is the fallback and the periodic cross check rather than the primary |

**Open:** which signals to build first, pending the verification items in section 9.

### The battle sequence, refined

Accounting for the states above changes the battle loop from what section 5 describes:

```
pre battle scroll     decide fight / auto resolve / withdraw, declare the D6 intent
        v
battle deployment     UNTIMED. Formation, terrain, reserves, per the intent
        v
battle in progress    freeze tick loop, event driven with a floor
        v
post battle scroll    harvest outcomes, write the after action record
```

**The deployment phase is the find here.** It is untimed, so there is no clock to race, and it sets the initial conditions the whole battle proceeds from. That makes it the one point inside a battle where full deliberation is affordable: strategic prompt mode, reasoning allowed, retrieval from the experience corpus, as long as it needs. Every other battle decision is made under a 6 to 9 second budget.

It is also where the deterministic predictors earn the most, since terrain and matchup evaluation at deployment is exactly a one step prediction problem, which is what D10 left in scope.

## 6. Fair play, and why it matters technically

Most of the interesting console commands are cheats. `toggle_fow` and `toggle_perfect_spy` remove fog of war, `add_money` prints gold, `auto_win` and `force_battle_victory` decide battles outright. If the AI uses any of them, nothing it does afterwards means anything, and the harness numbers from the architecture document become meaningless.

So split the command surface explicitly in code, not by convention:

- **Allowed at runtime**: observation of things the player can see, movement and orders the player could issue, turn sequence control.
- **Allowed in evaluation only**: `toggle_fow` and `toggle_perfect_spy`, used to compute ground truth for scoring how good the agent's beliefs were, never fed back into the agent's own state.
- **Never**: money, instant construction, forced battle outcomes.

Make this a hard boundary in the actuator, with the cheat set behind a flag that the harness can read and that taints any run that used it.

Two other constraints worth writing down. This is single player only; automating multiplayer is cheating and is not something I will help build. And staying on the script, console and synthetic input path means never touching process memory, which keeps the whole project clear of the EULA questions that memory reading and code injection raise.

## 7. Where things run

The control loop is a local process on the gaming machine. It owns the log tails, the console, the input synthesis, and the abstraction search. Nothing in the fast path crosses the network.

AO and Reach are consulted asynchronously for the deliberation tier only, exactly as in the generic architecture: `client.director` for the directive, `client.narrator` for commentary, `client.opponent_modeler` for reading the opposing faction. The campaign turn boundary and the battle freeze are both natural places to fire a call and pick up the result later.

The cloud session is for development, not runtime. A screenshot round trip from a cloud agent to the game machine and back is hundreds of milliseconds at best, and that is fine for building and debugging this but cannot be in the loop.

## 8. Milestones, in dependency order

The LLM is the last thing to add, not the first. This project lives or dies on the observation and actuation harness.

1. **Telemetry spike.** Background script that dumps faction, settlement and army state at `NewTurnStart`. Tail `scripting_log.txt` from a Python process and reconstruct campaign state externally. Success is a state object that matches what is on screen for twenty consecutive turns. No AI.
2. **Actuation spike.** Drive one complete campaign turn end to end with console commands plus UI automation, hardcoded, no reasoning. Success is twenty turns without a desync between intended and actual action.
3. **Battle freeze loop.** `toggle_game_update`, `output_unit_positions`, parse, issue one order, resume. Success is a full battle fought at a fixed tick with no manual intervention.
4. **Abstraction and search.** Build the campaign simulator from the documented formulae. Start logging predicted against actual outcomes.
5. **Deliberation tier.** Only now add `client.director`. The harness from the architecture document compares search only against search plus directive, and the fair play boundary from section 6 is what makes those numbers mean anything.

## 9. Open questions

- Do `list_units` and `list_characters` write anywhere a process can read, or is the console pane the only sink?
- Is there any state change an external process can make that a background script can detect, which would unlock the tier 4 script primitives?
- Does the agent play a faction autonomously, or advise a human who stays in control? The second is much easier to make useful early and is a better demo.
- Which game version to pin. UI layout changes across patches will break the automation tier.

## Sources

- [FeralInteractive/romeremastered modding documentation](https://github.com/FeralInteractive/romeremastered)
- [Scripts guide](https://github.com/FeralInteractive/romeremastered/blob/main/documentation/feature_guides/scripts/Scripts.md)
- [Logging guide](https://github.com/FeralInteractive/romeremastered/blob/main/documentation/feature_guides/logging/logging.md)
- [Rome Remastered console commands](https://www.gamewatcher.com/total-war-rome-remastered-console-commands-cheats)
