# Bottleneck analysis and proposed resolutions

Written 2026-09-01. Seven constraints, ranked by how much they shape the architecture. Each has a recommendation and the reasoning behind it. Numbers are marked as documented or estimated.

**Decisions taken 2026-09-01:** B1 hybrid, event driven with a floor. B1b single model on the `ada` server, RTX 4000 Ada 20 GB. B2 composed views. B6 shelved, see the note in that section. B8 moot while B6 is shelved.

**Scope note.** The goal is an agent that plays Rome Remastered. Several items here were originally sized for proving architectural claims about the agent, which is a different and much more expensive question. Where that happened it is marked, and the analysis is retained rather than deleted so it is available if the goal ever changes.

## B1. Deliberation latency against decision frequency

**The master bottleneck. Everything else is downstream of this.**

A Reach round trip plus LLM inference is seconds. Estimate 2 to 4 seconds against a small local model on the Jetson, 4 to 10 against a large cloud model, both including transport and image handling.

The arithmetic that matters, all estimated:

| Context | Decision points | At 3s per deliberation |
|---------|-----------------|------------------------|
| Campaign turn | 20 to 50 actions | 60 to 150s, tolerable |
| 20 minute battle at a 3s freeze tick | ~400 ticks | 20 minutes of pure deliberation on top of the battle |
| 200 turn campaign | 4,000 to 10,000 actions | Days of wall clock |

Deliberating on every decision is not viable in battles and is marginal on the campaign.

**Recommendation: event driven deliberation, fixed tick local control.**

The local tier runs the battle at its own tick using search and the behaviour layer. AO is consulted only on phase changes, meaning first contact, a unit routing, a flank becoming exposed, reserves needing commitment, the enemy general dying, an unexpected reinforcement. Estimate 5 to 15 deliberations in a battle rather than 400. The directive stays valid between them, which is what `valid_for_plies` was for.

**Decided: hybrid, event driven with a floor.** Event triggers as above, plus a guaranteed deliberation every N seconds of battle time so the agent cannot go blind if the event detector misses something. Set the floor generously, meaning 30 to 60 seconds of battle time rather than 3, for the reason in B1b below.

## B1b. Deliberation compute, single local model

**Decided: one model, served from the `ada` server on the same network. NVIDIA RTX 4000 Ada Generation, 20 GB GDDR6, 360 GB/s, 130 W.**

Documented capacity: at Q4_K_M, 20 GB holds models up to roughly 31B with context headroom, and the card benchmarks around 42 tok/s on an 8B at Q4_K_M.

Token generation is memory bandwidth bound, so the rest follows from 360 GB/s. Estimated, single stream:

| Model | Weights at Q4 | Generation |
|-------|---------------|-----------|
| 8B | ~4.7 GB | ~42 tok/s (measured, per the benchmark above) |
| 12B | ~7.1 GB | ~28 tok/s |
| 27B to 31B | ~16 to 18 GB | ~12 tok/s, and tight once the KV cache grows |

**Output length is the dominant latency term, and it is the one you control.**

A deliberation call is prefill plus generation. Prefill with four to six composed views is roughly 4,000 to 10,000 vision tokens, estimated at 2 to 5 seconds. Generation at 28 tok/s on a 12B is where the time actually goes:

| Directive length | Generation time |
|---|---|
| 100 tokens | ~3.6s |
| 300 tokens | ~11s |
| 800 tokens with visible reasoning | ~29s |

So a terse directive lands in 6 to 9 seconds total and a chatty one takes half a minute. That is a 3x latency lever available purely from the response schema.

**Recommendation: two prompt modes, one model.** This respects the single model decision while recovering most of what the fast/slow split would have given.

- **Tactical mode**, used at battle events. Constrained output, no visible reasoning, budget 100 to 150 tokens. Target 6 to 9 seconds.
- **Strategic mode**, used at campaign turn boundaries where latency is free. Reasoning allowed, budget 800 or more tokens. Half a minute is fine when nothing is waiting.

Three further consequences.

**The battle floor has to be generous.** At 6 to 9 seconds per tactical call, a 30 to 60 second floor is right. A 3 second floor would mean the battle never runs.

**The directive contract matters more, not less.** A 12B class model is decent at posture, weights and reading intent, and bad at precise tactics. The original design already keeps it away from move selection, which turns out to be load bearing rather than merely tidy. Resist widening what the model decides.

**Keep the seam swappable.** AO's catalog is model agnostic and already has a `vllm` provider type, so pointing the director at a larger or remote model later costs configuration and nothing else. Do not build anything that assumes this model's latency or context window.

The honest expectation: a local 12B class model is more likely to cost Elo than to add it, and the value it delivers is legibility, character and adaptation. That is what B6 is for.

### Topology

The Windows box runs the game and the host app. The `ada` server runs the model. The open question is where the AO engine sits.

**Recommendation: co-locate the AO engine on `ada`.** That puts the engine next to the GPU, so composed view payloads never cross the network twice, and it leaves exactly one network hop on the path, which is the Reach WebSocket from the Windows box. LAN latency there is negligible against a 6 to 9 second inference. mTLS enrollment is then between the Windows box and `ada`, which is the flow already documented in the platform context.

**Why this over the alternatives.** Speculative deliberation, meaning firing calls on predicted future states, sounds attractive but multiplies cost by the branching factor and is wasted whenever the prediction misses, which under fog is often. Batching multiple decisions into one call reads well until the first decision invalidates the rest. Event driven is the only option where the cost scales with how much is actually happening.

## B2. Vision payload budget

**Documented:** Reach caps a turn at 16 images, 4 MiB each, 20 MiB total.

**Estimated:** a 1440p PNG screenshot runs 3 to 8 MiB, so two or three raw grabs exhaust the turn. The same view at 1280x720 JPEG q80 is 150 to 300 KiB, which fits sixteen inside 5 MiB.

Encoding choice alone moves this by more than an order of magnitude, and resolution above roughly 1500px on the longest edge buys very little, since providers generally downscale before inference anyway. Sending 4K is pure waste.

**Recommendation: a view compositor, not a screenshot sender.**

Rather than sending raw full screen grabs, compose a single image from the pieces that carry decision relevant information: the contested area at usable zoom, the minimap, the relevant unit cards, and the current selection. At the same pixel budget a composed view carries far more than a raw frame, because most of a raw frame is empty terrain and UI chrome the model does not need.

Standardise on roughly 1280x720 JPEG at q80 per view, budget four to six views per deliberation, and spend the remaining headroom on more viewpoints rather than more pixels per viewpoint.

**Why.** The cap is not the real constraint once you stop sending waste. The real constraint is that vision inference on a large image costs seconds, so fewer and denser beats more and sparser on both axes at once.

## B3. Action verification cost

`SendInput` can fail silently under UIPI, which is documented, so every action needs verification. If verification means a screenshot, the vision budget from B2 gets spent on bookkeeping rather than on understanding.

**Recommendation: optimistic execution with periodic reconciliation.**

Borrow the database pattern. Execute a batch of actions optimistically. Verify the aggregate result once against a cheap structured channel, meaning a log line or a console query. Only when the cheap check disagrees do you escalate to a screenshot to find out what actually happened, and then re-derive state and retry.

Tier the checks explicitly:

| Tier | Cost | When |
|------|------|------|
| Structured, log or console | Near zero | Default, every batch |
| Vision, single composed view | Seconds plus budget | Only when the structured check disagrees |
| Full re-observation | Expensive | Only after a failed retry |

**Why.** Per action screenshot verification would consume the entire vision budget and most of the wall clock while telling you almost nothing most of the time, because most actions succeed. Pay for verification in proportion to how often it fails, not how often it runs.

## B4. Script telemetry cost inside the game engine

This one only shows up if you know the engine. The Rome script interpreter is slow, and a background script doing `for_each` across every settlement and character on every `NewTurnStart` will add visible time to turn processing. Feral's own documentation warns that verbose script logging gets very large over an extended session, which is the same problem from the disk side.

**Recommendation: full dump on a slow cadence, deltas every turn.**

Emit a complete state dump every N turns, five or ten, and per turn emit only what the script can cheaply detect as changed. Keep `verbose_script_logging` behind a debug flag rather than on by default, and rotate the log files.

**Why.** Telemetry that makes turns take twice as long makes the whole project less pleasant to work on and skews any wall clock measurement you take. The belief store can carry state forward between full dumps, which is exactly what a belief store is for.

## B5. Simulator fidelity against rollout depth

> **Moot as of 2026-09-01, decision D10.** There is no tree search and there are no rollouts, so prediction error never compounds. The deterministic predictors only have to be accurate one step ahead, which is what the published formulae give directly. The prediction log is still worth keeping, for the reasons in B6's note. The analysis below applies only if search is added later.


The abstract simulator has to be fast enough to roll out thousands of times and faithful enough to be worth rolling out. Those pull against each other, and model mismatch compounds with depth, so deep rollouts in an approximate model are worse than shallow ones, not better.

**Recommendation: cap the horizon by measured accuracy, not by compute budget.**

Start shallow, meaning one to three campaign turns and ten to twenty seconds of battle. Log every prediction against the observed outcome from day one, before anything consumes the log. Extend the horizon only where the prediction log shows the model still holds at that depth. When accuracy falls below a threshold at depth N, the search is capped at N minus one regardless of how much compute is spare.

**Why.** The tempting failure is to spend the compute you have. A model that is 90 percent accurate per step is 59 percent accurate at five steps and 35 percent at ten, so search depth past the model's honest horizon is confidently wrong rather than uncertain, which is worse.

## B6. Evaluation throughput

> **Resolved 2026-09-01: shelved.** The two tier harness below was sized for the hardest question the project could eventually ask, which is whether the deliberation tier costs or adds Elo against an otherwise identical agent. That is a small effect and it needs thousands of games. It is not the current goal.
>
> **Current position.** Evaluation is watching it play, plus an optional "does it beat the vanilla Rome AI" check at 20 to 30 games when a number is wanted. Sample size scales with effect size, and that comparison is a large effect:
>
> | True win rate | Complete games to beat a coin flip at 95% |
> |---|---|
> | 90% | 8 |
> | 80% | 11 |
> | 70% | 18 |
> | 65% | 30 |
> | 60% | 71 |
> | 55% | 281 |
>
> **Keep two things anyway**, because they cost nothing now and cannot be reconstructed later: the intent record, which separates a bad observation from a stale belief from bad reasoning from a silent actuation failure, and the prediction log, which is the only data that could ever make the simulator trustworthy.
>
> **The simulator keeps its priority** for the original reason, meaning it is the search substrate that makes the agent play well. Evaluation was always its second job.
>
> The analysis below is retained for the point where strength claims start being made. Do not act on it before then.

### The problem, stated plainly

You want to know whether the deliberation tier helps or hurts. The only way to know is to play games and count wins. The question is how many games "enough" is, and the answer is much larger than intuition suggests, because single game outcomes are extremely noisy.

Standard error on an Elo estimate near even strength is about `347 / sqrt(N)`. Worked out:

| Games played | Standard error | 95% interval | Smallest gap you can actually detect |
|---|---|---|---|
| 20 | 78 Elo | ±152 | 305 Elo |
| 40 | 55 Elo | ±108 | 215 Elo |
| 100 | 35 Elo | ±68 | 136 Elo |
| 400 | 17 Elo | ±34 | 68 Elo |
| 1,000 | 11 Elo | ±22 | 43 Elo |
| 5,000 | 5 Elo | ±10 | 19 Elo |

The effect you are trying to measure, meaning what the deliberation tier costs or adds, is plausibly 20 to 50 Elo. Reading that table, you need somewhere between 1,000 and 5,000 games per arm.

### Why the real game cannot supply that

A Rome campaign is hours of wall clock for a human, and considerably more for an agent that freezes to deliberate. Even being generous, a realistic budget is tens of games, not thousands.

At 40 games you cannot detect anything smaller than 215 Elo. So a real game only harness does not measure the deliberation tier's effect badly, **it cannot measure it at all.** The central question of the project comes back as "no significant difference" regardless of the truth. That is the decisive argument, and it is arithmetic rather than opinion.

### The proposal

Two tiers with a calibration link between them.

**Tier 1, the abstract simulator.** Thousands of games per arm, cheap and fast, run on every meaningful change. This is where the four arms are compared and where iteration happens.

**Tier 2, the real game.** A small sample, perhaps 20 to 40 games. Its job is **not** to measure strength, which at that sample size it cannot do. Its job is to measure **agreement** with tier 1.

### What calibration actually checks

Three things, in increasing order of how much you should care:

1. **Outcome agreement.** Given the same starting position, does the simulator predict what the real game did?
2. **Magnitude agreement.** Is a 50 Elo gap in the simulator roughly a 50 Elo gap in the game, or is it compressed or exaggerated?
3. **Ranking agreement.** Do the four arms come out in the same order in both?

Number 3 is the one that matters. **The simulator does not need to be accurate, it needs to be order preserving.** You are not asking it "how strong is this agent", you are asking it "which of these two agents is better". That is an ordinal question, and it is a far weaker requirement than absolute fidelity, which is why this works at all.

### Prior art for the pattern

This is not a workaround, it is how expensive-to-test engineering normally works. Aerodynamics simulates thousands of designs and puts a handful in a wind tunnel, where the tunnel validates the simulator rather than each design. Closer to home, chess engine development tunes on millions of games at very short time controls and validates on far fewer games at long time controls, on exactly this ordinal assumption.

### Why this raises the simulator's priority

The abstract simulator stops being just the search substrate and becomes the evaluation environment as well. That makes it the most load bearing component in the project and argues for building it earlier than its position in the milestone list suggests.

It also means B5 and B6 share machinery. Every prediction against outcome logged during real play is free calibration data, so the discipline recommended in B5 pays for itself twice.

### The failure mode to guard against

If you tune the agent purely against the simulator, you risk tuning it to exploit the simulator's errors rather than to play Rome. The tier 2 sample is what catches this, which is why it is not optional and why ranking agreement is the check that matters. If the ranking diverges, you have found a simulator bug, and that is a useful result rather than a wasted run.

### Real game levers

`ai_turn_speed` sets a multiplier on AI turn processing, and auto resolve avoids fighting battles you are not measuring. Both help the tier 2 sample go faster, neither changes the arithmetic above.

## B7. Console output sink

**Status: unknown, and blocking.** Where do `list_units` and `list_characters` actually print? If they go only to the in game console pane, reading them needs OCR, which is slow and error prone and would knock that channel down a tier.

**Recommendation: resolve by experiment, but the risk is lower than it looks.**

Run the check early. But note that the background script channel largely supersedes these commands anyway, since `for_each` over settlements and characters plus `script_log` produces the same information in a file that is trivially parseable. If the console prints nowhere useful, the loss is on demand querying rather than the state feed itself.

**Why this ranks last despite being unknown.** It is the only item here with a good fallback already designed in.

## B8. Harness throughput with the model in the loop

**New, surfaced by fixing the compute budget in B1b.** B6 says run thousands of games per arm in the simulator. That is cheap for the search only arm, which makes no model calls at all. It is not cheap for the three arms that include the deliberation tier.

The arithmetic, estimated:

- 1,000 simulated games at roughly 15 deliberations each is 15,000 calls per arm
- At 13 seconds single stream that is 54 hours per arm
- Three model bearing arms is about a week of continuous GPU time per harness run

A harness you can only run weekly is not a harness, it is a ritual. Four resolutions, and they compound.

**1. Serve with vLLM rather than Ollama for harness runs.** Continuous batching lets concurrent simulated games share each weight read, so aggregate throughput scales far beyond single stream. At batch 16 to 32 this is plausibly a 10x or better improvement, taking a week down to well under a day. AO already has `vllm` as a provider type reading `VLLM_BASE_URL`, so this is a catalog entry rather than new architecture. Ollama stays fine for interactive play, where there is only one stream anyway.

**2. Paired comparison, meaning common random numbers.** Run every arm against the same starting positions and the same opponent seeds. Position difficulty then cancels between arms instead of adding noise, which cuts the games needed for a given confidence, plausibly by two to four times. This is standard variance reduction and costs nothing but bookkeeping.

**3. Directive caching.** Many simulated positions are strategically near identical. Cache directives against a coarse state signature, meaning posture relevant features rather than exact state. Cache hits cost nothing and the hit rate in a simulator sweep should be high.

**4. Unequal sample sizes.** Give the search only arm 5,000 games because it is nearly free, and the model bearing arms 1,000. The comparisons that matter are between arms, and the cheap arm being measured precisely tightens every comparison it appears in.

Together these turn a week per run into hours, which is the difference between a harness that guides the work and one that audits it afterwards.

## Summary

| # | Bottleneck | Recommendation |
|---|-----------|----------------|
| B1 | Deliberation latency vs decision frequency | **Decided.** Hybrid: event driven with a generous floor, fixed tick local control |
| B1b | Deliberation compute | **Decided.** Single model on `ada`, RTX 4000 Ada 20 GB. Two prompt modes, terse tactical and reasoning strategic. Co-locate the AO engine on `ada` |
| B2 | Vision payload budget | **Decided.** View compositor at ~1280x720 JPEG q80, four to six composed views per call |
| B3 | Action verification cost | Optimistic execution, cheap structured verification, vision only on disagreement |
| B4 | Script telemetry cost | Full dump every N turns, deltas per turn, verbose logging behind a debug flag |
| B5 | Simulator fidelity vs depth | **Moot.** D10 removed tree search, so error never compounds |
| B6 | Evaluation throughput | **Shelved.** Watch it play, plus an optional 20 to 30 game check against the vanilla AI. Keep the intent record and the prediction log |
| B7 | Console output sink | Resolve by experiment, script channel is the fallback and covers most of it |
| B8 | Harness throughput with the model in the loop | **Moot while B6 is shelved.** Revisit only if the full harness is ever run |
