# Analysis — 20260909-220705 (no code changes)

Evidence only. Findings below cite files in this fixture and Ada run traces.

---

## Issue 1 — Attempt 7 End Turn fault

### Sequence (from `runtime/phase2_live_20260909-220705.log`)

1. Attempt 6 completed; Rome handed turn 7 back.
2. Attempt 7 sync: map clear, then **modal** `left_overlay_panel` → close X → “cleared”.
3. Ready check: `ui=campaign_map`, End Turn attempted.
4. `RomeShell: end_turn failed (no_turn_boundary)` → attempt FAIL.
5. Attempt 8 sync: still **modal**; specifically **`VISION scroll: floating notice`** then another left panel close.
6. After that, End Turn **succeeded**; wait began for turn 8.
7. Process then crashed in `wait_for_turn_event` → `load_config` → YAML composer error (trail traceback at end of phase2 log). Rome still wrote `Turn 7 End.sav` / `Turn 8 Start.sav` (see `rome_logs/rome_paths_meta.json`).

### Rome log (`rome_logs/message_log.tail.txt`)

Around Turn 7 Start: marriage / trait spam, `IncomingMessageType needs an event` repeated many times (UI event queue noise), then `between turns` and `Turn 7 End.sav`. After End: `Trying to reinitialise the own_character_info_scroll when it hasn't been initialised already` (console `list_characters` side effect).

### Ada?

Not an Ada/AO failure for End Turn. End Turn is local Process A actuation. Ada traces for this window are only `direct_agent` start/end for the campaign director.

### Conclusion (supported by logs)

Attempt 7 pressed End Turn while a **floating notice / left overlay was still (or again) up**. Local vision said map clear after one X click; attempt 8 proves a floating notice was still present. Failure mode is UI readiness, not turn-marker math (mtime-based saves advanced on attempt 8). The later YAML crash aborted the run while waiting for the next Julii turn.

---

## Issue 2 — Director always `hold`

### F1 — Payload diff (2026-09-10)

Command: recompose from frozen `belief/belief_snapshot.json` + `runtime/campaign_id_map.json` for consecutive deliberate turns (`campaign-2-72f20f55` turn 2 vs `campaign-3-ae56ba54` turn 3), then byte-diff the full composed payloads.

**Verdict: identical (belief body frozen).**

| Comparison | Result |
|---|---|
| Full payload byte-identical | No — only `question_id` and `turn` lines differ |
| Body after stripping `question_id` / `turn` / `state_hash` | **Byte-identical** |
| `state_hash` / belief block | `90a0b9f8` both turns |
| STANDING / THREATS / YOU HOLD / GENERALS / CANDIDATES | Unchanged |
| TREASURY / INCOME | Absent both turns (never passed into compose) |
| Payload ages | All `age 0` (no `last_seen_turn` on entities) |

Ada traces do not store the prompt body; prompt_tokens stayed ~978–984 across six calls, consistent with a near-static brief. Because Rome advanced game turns while the hashed board and every non-meta payload line stayed fixed, **F3 applies**. Repeating `hold` against this brief is consistent answering of the same question, not model oscillation — but the brief itself was not advancing as the belief contract requires.

### What Process B recorded (`runtime/deliberate_20260909-220705.log`)

Every accepted directive: `objective=hold`, same `state_hash=90a0b9f8`. Example becauses:

- “no immediate threats and no strong candidates to reinforce or besiege”
- “no general is idle or near a settlement with a weaker garrison”
- “no candidate to prioritize”
- “candidates: no settlement threatened by a hostile stack within 2 turns' march”

None were rejections (`unknown_id`, `downgraded`, `malformed`). Accept path took the model’s hold as-is.

### What the belief actually contained

Recomposed from `belief/belief_snapshot.json` → `reconstructed_payload.txt`:

- `state_hash`: **90a0b9f8** (matches the deliberate log)
- **5 candidates**, including `set_segesta … 1 turns … garrison weaker`
- **4 free generals** (Flavius near Arretium, Lucius/Quintus idle, …)
- Threats: `none observed`

So the deterministic brief **did** offer a clear `besiege` candidate. Belief was not empty (`campaign_setup` seed present). `bootstrap_from_logs: 0` only means no prior log ingest; seed filled the store.

### Ada evidence (`ada/traces/*.jsonl`)

For `campaign-2-72f20f55` (run `f74d0bd0…`):

- Agent: `client.campaign_director`, model `llama3.1:8b`, `ok: true`
- `prompt_tokens` ≈ **982**, `completion_tokens` ≈ **28**
- Not a timeout; call finished in ~10s then later calls in ~1–2s
- Engine preview shows the ROLE/backstory question text; full prompt is not stored in the trace
- Token count is consistent with question + composed payload + schema (local char estimate ~800 tokens at 4 chars/token; Llama tokenizer higher → ~982 is plausible **with** context included)

`game_query` was not used on these JSON-mode calls (`mcps: null`; deliberate log `calls=0`). Stale `game_query_usage.jsonl` rows are from earlier sessions (placeholder army ids), not this run’s director path.

### Conclusion (supported by logs)

1. **F1:** Belief body frozen across turns (identical after stripping turn/qid). Ages stuck at 0; treasury absent. Pipeline defect, not model oscillation.
2. **Not** Ada rejecting or timing out. Traces show successful `direct_ollama` completions.
3. Independently, the model **answered hold while denying or redefining candidates** against a brief that listed five. That remains a model/input failure mode (see F4–F6).
4. Accept trusted the hold (F7 floor).
5. Secondary: Process A often adopted hold / “directive expired after 1 plies” between B’s writes — so even a late besiege would race a 1-ply hold window — but that does not explain why B never issued besiege.

---

## Fixture purpose

Use this directory to build an e2e test that:

1. Asserts payload composition from the saved belief always surfaces `set_segesta` (and hash `90a0b9f8`).
2. Treats recorded hold becauses that claim “no candidates” as **failing** behavior against that payload.
3. Replays attempt-7 UI sequence expectations (modal/floating notice before End Turn).
