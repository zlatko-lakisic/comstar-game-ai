# Campaign run fixture — 20260909-220705

Frozen evidence from a live Julii Phase-2 run (`python scripts/run_phase2_actuation.py --directives --seconds 12 --deliberate-interval 35`).

**Do not mutate these files.** Treat them as the source for an end-to-end regression fixture before the next live campaign.

## What happened (operator-visible)

- Telemetry OK; fresh campaign (bootstrap_from_logs: 0).
- Attempts 1–6: End Turn worked; Julii advanced (game_turn 2 → 7).
- Attempt 7: End Turn failed (`no_turn_boundary`); attempt failed.
- Attempt 8: cleared floating notice / left panel, End Turn succeeded, then the process crashed mid-wait (YAML composer error while reloading config — see trail traceback).
- Every AO directive accepted this run was `hold`. No `move_character`.

Newest Rome autosaves at archive time: `Turn 8 Start.sav`, `Turn 7 End.sav`.

## Layout

| Path | Contents |
|------|----------|
| `runtime/phase2_live_*.log` | Process A trail |
| `runtime/deliberate_*.log` | Process B AO accept log |
| `runtime/directive.json` | Last directive on disk |
| `runtime/campaign_id_map.json` | Id ↔ name map |
| `runtime/phase2_report.json` | Prior report file present in runtime (copied; may be from earlier run — check mtime) |
| `belief/belief_snapshot.json` | BeliefStore after the run |
| `intent_records/handoff_*.jsonl` | Intent record for this session |
| `rome_logs/*.tail.txt` | Last 200KB of message_log / scripting_log |
| `rome_logs/rome_paths_meta.json` | Paths, sizes, newest saves |
| `reconstructed_payload.txt` | Payload recomposed from this belief (same `state_hash`) |
| `ada/traces/*.jsonl` | AO engine run traces for each director call |
| `ada/engine_probe.txt` | Engine log grep for question_ids |
| `ANALYSIS.md` | Investigation notes (fault + perpetual hold) |

## How to reuse

1. Load `belief/belief_snapshot.json` into BeliefStore.
2. Compose payload; assert `state_hash == 90a0b9f8` and `CANDIDATES` contains `set_segesta`.
3. Replay accept path against recorded `because` strings / expected objectives once a golden response corpus exists.
4. Drive modal/end-turn regressions from the attempt-7 sequence in the phase2 trail.
