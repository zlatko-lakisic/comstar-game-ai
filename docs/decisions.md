# Architecture decisions

Decisions taken 2026-09-01, with consequences and one open amendment. Companion to `smart-player-architecture.md` and `rtw-remastered-integration.md`.

## The four decisions

| # | Decision | Chosen |
|---|----------|--------|
| D1 | Autonomy model | Fully autonomous with a declared intent record, no approval gate. Amended 2026-09-01, see C5 |
| D2 | Primary layer | Both campaign and battles, over a shared core |
| D3 | Observation structure | Portable state contract, per game providers |
| D4 | Information model | Fogged, the agent sees what a human player would see |
| D5 | Evaluation source | Outcome grounded. The game state says whether a move was good, not an authored heuristic |
| D6 | Battle intent | The agent declares the battle result it is playing for. Aggression is derived from that target, not set directly |
| D7 | Doctrine ingestion | Strategy write ups and tactics documentation found online feed the agent, as priors to be tested rather than as truth |
| D8 | Continuous experience learning | The corpus is updated continuously with decisions and outcomes, from the agent's own play, the game's native AI factions, and the human |
| D9 | Battle tick rate | Unthrottled. The agent freezes and acts as fast as it can. Mechanical superiority in micro is accepted deliberately |
| D10 | Search scope | No tree search. Deterministic one step predictors only, consulted by the reactive layer |
| D11 | Corpus location | Both doctrine and experience corpora live on AO |
| D12 | Consolidator | Writes doctrine directly, no review gate |

D3 amended 2026-09-01: keep the portable contract, and let it take Rome's shape where Rome forces it. Generalise when a second game actually arrives rather than in advance.

Together these are the most demanding combination available. D4 is what makes the project intellectually real, and it is also what makes D1 expensive. That interaction is the subject of the open amendment below.

## C1: the contract is a belief contract, not a world state contract

This is the largest consequence of D4 and the easiest to get wrong by retrofitting.

Under fog, the agent never holds the world state. It holds a belief about the world state, assembled from partial observations of differing age and reliability. That is not a detail of the observation layer, it reaches all the way up. So the portable contract from D3 carries, on every entity:

- **Provenance**: which channel supplied this, script telemetry, console query, vision, or inference
- **Age**: when it was last directly observed, in turns or seconds
- **Confidence**: how much to trust it now, which decays differently per attribute
- **Existence status**: observed present, believed present, believed destroyed, never seen

An enemy army is not a position. It is a last known position, a time since observation, a movement range implied by that elapsed time, and a composition estimate that may be several turns stale. The simulator from the architecture document therefore does not roll out from a state, it rolls out from a distribution over sampled states. That is a materially different simulator and it should be designed that way from the start rather than wrapped in uncertainty later.

Getting this right at the contract level is cheap now and very expensive after two layers depend on the wrong shape.

## C2: scouting becomes a first class action class

Under perfect information, actions are chosen for their effect on the world. Under fog, some actions are chosen for their effect on the belief. Spies, scouting cavalry, diplomat movement, keeping a unit on a hill for visibility, and choosing to attack partly to learn what is defending are all information acquisition, and they compete for the same movement points as everything else.

The planner has to be able to value information, not just outcomes. This is the single largest piece of design work D4 adds, and it does not exist at all in the perfect information version.

## C3: what "shared core" should mean, given D2

The campaign is turn based with unlimited deliberation time. Battles are frozen tick with seconds. Their observation channels, actuation surfaces and simulators have almost nothing in common. An abstraction spanning all of that will fit neither layer.

So share the reasoning, not the plumbing. Concretely:

**Shared**

- The belief state and its contract, including the decay and provenance model
- The directive contract, meaning posture, objective weights and priors
- The deliberation tier, the AO Reach agents and the prompts that drive them
- The evaluation harness, its arms and its metrics

**Per layer**

- Observation providers
- Actuation surfaces
- The simulator and its search
- The control loop and its cadence

The strongest argument for sharing the belief state specifically is that battles happen inside the campaign. What a battle reveals about enemy composition is campaign knowledge, and what the campaign knows about a faction's reserves is battle context. If the two layers hold separate beliefs, that information is lost at exactly the boundary where it is most valuable. One belief state crossing the boundary is the thing that makes "both layers" more than two projects in a trench coat.

## C4: a new evaluation metric, belief accuracy

D4 unlocks a measurement that the perfect information version cannot have. The evaluation harness may use `toggle_fow` and `toggle_perfect_spy` to compute ground truth, never feeding it back to the agent, and score how wrong the agent's beliefs were.

That gives a three way error attribution the project would otherwise lack:

- Belief was accurate and the decision was still bad, so the reasoning is at fault
- Belief was wrong and the decision followed correctly from it, so the observation or decay model is at fault
- Belief was wrong in a way the agent should have known was uncertain, so the confidence model is at fault

Without this, every mistake looks the same from the outside. This metric sits alongside Elo and legibility from the architecture document.

## C5: open amendment on D1, recommended

D1 chose direct action and rejected the veto. That is a reasonable call and I am not relitigating autonomy.

But the veto was not the valuable part of that option. The intent record was. I recommend keeping the intent record and dropping the veto, which preserves full autonomy at no latency cost:

```
decide -> declare intent -> execute immediately -> observe outcome
```

No human in the loop, nothing waits. The agent simply states what it is about to do and why before it does it.

The reason this matters is specific to D4. Under fog, when the agent does something that looks stupid, there are four candidate causes:

1. It observed wrongly, meaning the channel failed
2. It observed correctly but believed something false, meaning the decay or inference model failed
3. Belief was fine and the reasoning was bad
4. Everything upstream was fine and the actuation misfired, so it did something other than what it meant to do

With direct action and no intent record, all four produce the same symptom, which is a bad thing happening on screen. With an intent record, they separate cleanly, because you can compare intent against belief and intent against outcome independently. Cause 4 in particular becomes invisible without it, and it is the most likely failure mode in a project driving a commercial game through synthetic input.

The intent record is also what makes the legibility metric computable, and it is the natural payload for the narrator agent, which needs to know what the player meant, not just what happened.

**Status: accepted 2026-09-01.** D1 now reads "fully autonomous with a declared intent record, no approval gate." Every action is declared before it executes, nothing waits on a human, and the record is what separates the four failure causes above.

## C6: what D5 replaces, and what it cannot

D5 rejects authored evaluation. Nobody writes down that material is worth 1.4 times tempo. The game decides what went well.

### What the game actually supplies

More than assumed. These are all engine computed, not opinions.

**Campaign, every turn**

| Signal | Source |
|--------|--------|
| Faction scores | `dump_fac_score`, outputs to the debug stream, so it lands in the log |
| Faction ranking over time | The game maintains a ranking graph, interval set by `set_ranking_interval` |
| Settlements, treasury, army strength | Background script telemetry |
| Region fertility | `dump_fertility` |
| Campaign victory or defeat | Terminal |

**Battle**

| Signal | Source |
|--------|--------|
| Battle ended | `I_BattleEnd`, `I_BattleEndPending`, `I_BattleFinished` script events |
| A unit routed | `UnitHasRouted` condition, `BattleUnitActionStatus <unit>, routing` |
| Battles fought to date | `LocalPlayerBattlesFought` |
| Unit strengths over time | `output_unit_positions` sampled across the battle |

So the reward is not one bit per two hundred turns. It is a scalar every turn plus a strong signal per battle plus per unit rout events inside battles. That is dense enough to be learnable at realistic sample sizes, which pure terminal reward would not be. AlphaZero needed on the order of tens of millions of games to learn from terminal outcomes alone, with a perfect fast simulator. Neither condition holds here.

### How value gets learned instead of authored

**Learn state features to eventual outcome.** The label is a game computed measure at horizon k, or the terminal result. No hand tuning.

**Bootstrap from the vanilla AI.** The cold start problem, needing a decent policy to generate games and games to learn value, is solved by not needing your agent at all. Let the shipped Rome AI play, log state against outcome, and you have a training set before the agent plays a single turn. The game generates its own supervision.

**Reuse the prediction log.** The logging discipline already agreed for B5 and B6 is the same machinery. Log state features now, outcome later, and the training set accumulates as a side effect of playing.

### The directive contract has to change

This is the concrete consequence. `objective_weights` over named evaluation terms was authored evaluation wearing a schema, and it goes.

What replaces it is a preference over the outcome space the game already defines, not a redefinition of it:

- **horizon**: how far ahead outcomes are valued, meaning the discount rate
- **risk posture**: variance preference over the same outcome distribution

The distinction matters. "Accept casualties to break them now" is a horizon and risk statement about outcomes the game measures. "Material is worth 1.4 times tempo" asserts what good means. The first is a legitimate thing for the deliberation tier to say. The second is what D5 rules out.

`focus_actions`, `avoid_actions` and `opponent_read` are unaffected. They are priors and beliefs, not evaluations.

### What cannot be eliminated, stated honestly

Two choices survive and someone has to make them:

1. **Which game computed measure is the target.** Faction score, settlements held, survival, or terminal victory.
2. **Over what horizon it is measured.**

These are authored. The gain is that it is two explicit knobs instead of a dozen hand tuned weights, and both are empirically testable: does optimising faction score at twenty turns actually correlate with winning campaigns? That is answerable from logged games rather than by argument.

**One caution on the game's own score.** `dump_fac_score` is Rome's opinion, and the shipped AI is not strong. Optimising it might mean optimising toward what a mediocre AI thinks is good. Check that faction score correlates with actually winning before trusting it as the target.

### Why this also helps D3

Outcome grounded evaluation is more portable than authored heuristics, not less. Every game has a win condition and most expose some score. Authored evaluation terms are per game and transfer to nothing. So D5 and the amended D3 reinforce each other.

## C7: battle intent replaces posture

D6 says the agent decides what result it wants from a battle, and that target dictates how aggressive it is. This replaces the `posture` field in the directive contract.

### Why this is better than an adjective

"Be aggressive" is a mood and cannot be checked afterwards. "Destroy this army completely, I will spend up to 40 percent of mine to do it" is a specification. Aggression then falls out of it as a computation rather than being asserted separately.

It also sits exactly inside what D5 permits. Declaring a target outcome selects a point in the outcome space the game already measures. It does not author a new definition of good.

### Total War battles are not binary, which is what makes this work

The strategically distinct goals are genuinely different, and the game measures all of them:

| Intent | What success means | Typical situation |
|--------|--------------------|-------------------|
| Annihilate | Enemy army destroyed, few escape | They must not retreat and rebuild |
| Win cheaply | Victory with own losses minimised | Veterans are needed for a siege next turn |
| Hold | Survive N minutes, position kept | Buying turns for reinforcements elsewhere |
| Bleed and withdraw | Inflict losses, extract the army intact | Attrition without committing |
| Capture or kill the general | Enemy general dead | Succession crisis, faction leader targeting |
| Take the settlement | Walls and centre held | Siege, garrison secondary |
| Survive | Maximum extraction from a losing position | Outnumbered, no reinforcement |

### Shape of the intent

```json
{
  "objective": "annihilate | win_cheaply | hold | bleed_and_withdraw | capture_general | take_settlement | survive",
  "acceptable_own_losses": 0.35,
  "required_enemy_losses": 0.90,
  "hold_for_seconds": null,
  "preserve": ["unit ids that must survive"],
  "abort_if": { "own_losses_exceed": 0.60, "general_dies": true }
}
```

Every field maps to something the engine computes: casualties from unit strength sampling, rout counts from `UnitHasRouted`, elapsed time, general alive or dead, settlement held. Nothing here is an opinion.

### How aggression is derived

The tactical layer reads the intent as a constrained optimisation rather than a mood. Two examples of how the same position produces different play:

**Annihilate** favours charging into unfavourable melee if it stops routers escaping, commits reserves early, pursues rather than reforms, and accepts flank exposure to close an encirclement.

**Win cheaply** prefers missile attrition, avoids melee until the enemy is shaken, lets them rout rather than chasing, and holds reserves.

### Three things this unlocks

**A real legibility metric.** The earlier proxy was whether the played move appeared in `focus_actions`. This is far stronger: did the battle end the way the agent said it would? That is what a human would actually judge it on.

**Self knowledge as a learning signal.** If the agent repeatedly declares "annihilate, 35 percent acceptable" and takes 70 percent, its model of its own capability is wrong in a measurable, correctable way. That is a training signal about the agent rather than about the game.

**The campaign to battle link made concrete.** The campaign layer knows why a battle matters, meaning this is their last field army, or I need these veterans intact for next turn. That reason produces the intent. This is the shared belief state from C3 doing visible work instead of being an argument.

### The intent must be revisable mid battle

Battles go wrong. If the plan was annihilation and a flank collapses, the intent should downgrade to extraction. The events that justify re-deliberating are precisely the events that might change the intent, which is the event driven trigger already decided in bottleneck B1. The two designs fit without modification.

### Guard: an intent is a prediction, and predictions can be self serving

A model that is bad at estimating relative strength will declare annihilation against a superior force and lose an army. So the intent is proposed by the deliberation tier and then checked by the deterministic layer against a feasibility estimate, at minimum a strength comparison, and either accepted or forced to downgrade.

This is the same safety pattern as search never losing access to a legal move, applied one level up. The model proposes, the deterministic layer validates.

### Fair play note

The intent has to be achieved by playing. `force_autoresolve_outcome`, `auto_win` and `force_battle_victory` remain in the never-allowed set from the integration document. Declaring a desired outcome and then making it true by console command is not the feature.

## C8: how doctrine documents enter the system

D7 wants strategy guides and tactics write ups from the web to inform the agent. The word "train" is ambiguous here and the naive reading is the wrong one.

### Fine tuning is the wrong tool

Fine tuning the local model on strategy prose teaches it to *talk* like a Total War guide. It does not teach it to play better, because prose about tactics and decisions under uncertainty are different things. It is also expensive on a 20 GB card, slow to iterate, and impossible to revise incrementally, since adding one new guide means retraining.

Not worth it. Everything below is cheaper, faster to change, and more effective.

### Three destinations, not one

The important move is triaging each document by what kind of knowledge it contains, because they belong in different places.

| Content type | Destination | Prompt cost | Example |
|---|---|---|---|
| **Rules and tables** | Extracted to structured form, consumed by the deterministic layer | **Zero** | Unit counter matrix, terrain modifiers, formation matchups, charge bonuses |
| **Doctrine that always applies** | AO agent skill, injected every call | Small and fixed | Keep cavalry in reserve for the rout. Phalanxes are vulnerable from flank and rear |
| **Situational reference** | AO RAG corpus, retrieved on demand | Variable, retrieval only | Faction specific matchups, unit stat tables, siege specifics |

Most people put everything in the second or third bucket. The first is where the value is, because a counter matrix is a lookup, not a paragraph, and feeding it as prose on every call is both lossy and expensive.

### The platform already has two of the three

This is configuration on the existing stack rather than new architecture.

**RAG sources**, at `config/rag_sources/`, one YAML per corpus. Backends `sqlite-fts`, `embedding` and `hybrid` with reciprocal rank fusion, all shipped. Modes are `inject`, where the harness prepends context, or `tool`, where the agent calls `rag_query`. Per source `top_k` and `max_tokens`, global budget via `AGENTIC_RAG_INJECT_MAX_TOKENS` defaulting to 6000. Chunks are tagged `[rag:{source_id}#{chunk_id}]` and the harness verifies every citation against chunks actually retrieved, which matters here because doctrine the agent claims to be following should be traceable.

**Agent skills**, at `config/agent_skills/`, inject markdown into task description or backstory with `inject.max_chars` to bound them. They add instructions, not tools.

Both merge extra directories through environment variables, so the doctrine corpus can live outside the main repo.

### Doctrine is a prior, not truth

This is the part that keeps D5 intact.

A strategy guide is somebody's opinion, often about a different game version, often about a mod, frequently contradicted by another guide. D5 says outcomes decide what is good. So doctrine enters as a **hypothesis with a confidence**, and the outcome log is what confirms or kills it.

Concretely: doctrine informs which actions get considered and which intents get proposed. It never sets the value of an outcome. If the guides say hammer and anvil always works and the outcome log says this agent does worse when it tries, the outcome wins and the prior's confidence drops.

That also gives the corpus a natural quality signal over time, derived from play rather than from how confident the author sounded.

### Provenance metadata is not optional

Every ingested document needs at minimum:

- **Source** and date
- **Game version**: original Rome, Remastered, or a specific patch
- **Mod**: vanilla or which overhaul
- **Confidence**, updated by outcome evidence

Without the version and mod fields the corpus quietly poisons itself, because a large share of Rome strategy writing online predates Remastered or assumes a total conversion mod with different unit stats.

### Two cautions

**Exploit tactics.** A meaningful fraction of Total War strategy writing describes abusing the AI: pathfinding exploits, siege tower cheese, withdrawal loops. Ingesting those will produce an agent that wins in ways that are unsatisfying to play against and that do not reflect any real skill. Worth an explicit filter decision rather than discovering it in a battle.

**Copyright.** Retrieving and analysing published guides for a private system is a different activity from redistributing them. Keep the corpus local, do not republish the source text, and be aware the distinction exists. Not legal advice.

### Prompt budget interaction

Bottleneck B1b established that prefill with composed views is already 4,000 to 10,000 tokens. Retrieved doctrine adds to that on every call. So keep always-on skill text short, keep retrieval sparse and cached, and push as much as possible into the structured destination where the prompt cost is zero. That is a third independent argument for the first bucket.

### Connection to D6

Doctrine's highest value use is proposing the battle intent. "Against a phalanx heavy army, do not try to annihilate frontally, bleed and flank" is exactly a doctrine statement that selects an objective from C7's table. That is the cleanest path from a document to a decision the agent actually makes.

## C9: what RAG can and cannot learn

C8 uses AO's RAG for the doctrine corpus, meaning what other people wrote. That is one of three kinds of learning and the least interesting one. The bigger use is indexing the agent's own experience.

### RAG is retrieval, not learning

Retrieval changes what the model *sees*. It does not change what the model *is*, and it does not change what the system believes a good outcome is. So RAG can improve **which intent gets proposed** and it cannot improve **tactical execution**, because execution is decided by search and the value function, which never read the corpus.

Keeping that straight prevents the common mistake of expecting a better corpus to fix bad play.

### But RAG becomes a learning substrate when you index experience

After every battle and every campaign turn, write an after action record: the situation, the intent declared, what actually happened, whether the intent was achieved. Index those. Next time a similar situation arises, retrieve the relevant past ones.

That is case based reasoning, and it has one property the learned value function from D5 does not: **it works from game one.** The value function needs many games before it says anything. Experience retrieval is useful immediately, is inspectable because you can read what it learned, and is revisable because you can delete a bad lesson.

AO's knowledge base was built for almost exactly this shape: store finalised outputs, query FTS on a new goal, inject concise snippets into planner context.

### Three layers of memory, learning different things at different speeds

| Layer | Learns | Speed | Mechanism |
|-------|--------|-------|-----------|
| Doctrine corpus | What people say works | Instant, static | AO RAG source, see C8 |
| Experience corpus | What happened when **this agent** tried it | From game one | AO RAG source over after action records, KB backed |
| Value function | What actually correlates with winning | Needs many games | Learned from outcome logs, see D5 |

All three feed intent selection. Only the third feeds evaluation.

### The failure mode: superstition

Naive experience RAG learns superstition. The agent wins a battle by luck, writes "the flanking manoeuvre worked", retrieves that forever, and builds doctrine on a coin flip. Selection bias in what gets written down makes it worse.

**The rule that prevents it, and it follows from D5: the model narrates, the game measures, and only the measured part is trusted.** Every after action record carries the engine computed outcome numbers, casualties, rout counts, objective achieved or not, alongside whatever the model wrote about it. Retrieval weights on the measured fields. The narrative is payload, not evidence.

Retrieval must also be able to surface failures, not only successes, or the corpus becomes a highlight reel.

### The retrieval key is the hard part

This is where experience RAG usually fails in practice. **Similar situation and similar text are not the same thing.** A plain FTS search over prose after action reports retrieves on vocabulary, so a report that happens to use the word "hill" a lot matches another one about hills, regardless of whether the tactical situation resembles it at all.

So each record needs a structured header the retrieval can match on, with the narrative underneath as payload. Candidate fields: numbers ratio, composition classes on both sides, terrain type, whether attacking or defending, the objective from C7, and general quality. AO's `embedding` and `hybrid` backends help, since they match on meaning rather than tokens, but structuring the record is the real fix and it is a design decision rather than a config one.

### Where AO's existing pieces fit, and where they do not

| AO feature | Fit |
|---|---|
| Knowledge base, `__orchestrator_kb__/kb.sqlite3` | **Good fit** for the experience corpus, with a structured record shape rather than free prose |
| RAG sources, `config/rag_sources/` | **Good fit** for both corpora. Use `embedding` or `hybrid`, not plain `sqlite-fts`, for the reason above |
| Orchestrator sessions | **Good fit.** One session per campaign is the natural mapping, giving the planner continuity across turns |
| Learning loop, `__orchestrator_learning__/stats.json` | **Wrong shape.** It nudges *provider selection* by task type. The project's docs are explicit that it is not model training. Nothing here needs to choose between agent providers |
| Answer cache, `AGENTIC_ANSWER_CACHE` | **Turn it off.** It short circuits a repeated goal to a cached answer. In a game the same question text in a different board state must never return a cached reply. This is an easy trap to miss |

### What this does not replace

None of it substitutes for the outcome grounded value function. Experience retrieval tells the deliberation tier what happened last time something looked like this. It does not tell search which of two positions is better. Those remain separate, and D5 governs the second.

## C10: continuous experience learning

D8 says the corpus is fed continuously with decisions and their outcomes, from three sources: the agent's own play, the game's native AI factions, and the human. The framing is that this is how a person learns. That is broadly right, and the places where the analogy breaks are where the design work is.

### Why observing other players is a bigger deal than it sounds

This quietly solves the sample size problem from a different direction than the one that failed.

Earlier the concern was that hundreds of complete games are unaffordable. But a single Rome campaign of 200 turns with twenty-odd active factions produces on the order of **four thousand faction turns of observable decisions**, each with a consequence that plays out over subsequent turns. The agent risks nothing to collect them and does not have to be any good to start.

That is a completely different data regime from learning only by playing, and it is the strongest argument for D8.

### Three sources, three trust levels

| Source | Volume | Strategic quality | Observability | Role |
|--------|--------|-------------------|---------------|------|
| The agent's own play | Low | Improving over time | Full | The only source reflecting the current agent |
| Native AI factions | **Very high** | Mediocre | Partial, plus `campaign_ai_log.txt` | Volume source for what follows from what, not for good strategy |
| The human | Low | Presumably good | Full | Small, high quality demonstration set, and a style model for opponent modelling |

The weighting matters. The native AI is a physics teacher, not a strategy teacher: it shows what happens when an army of composition X attacks a settlement of type Y, which is exactly the causal texture the value function needs, while its strategic choices should carry very little weight.

### The fog boundary, which is easy to breach by accident

D4 says the agent sees what a human player sees. Continuous learning from other factions creates a specific way to violate that without noticing.

The distinction to hold: **learning time information and decision time information are not the same thing.** Training on facts the agent could not have observed in the moment is legitimate and standard, since any model trained on eventual outcomes uses future information. Using them at decision time is cheating.

The trap is that a retrieval corpus injects its content into the prompt *at decision time*. So privileged material in the corpus leaks straight through the fog boundary.

**Rule: every record is split into an observable part and a privileged part.** Only the observable part is retrievable during play. The privileged part, meaning `campaign_ai_log.txt` decisions the agent could not see, fog lifted ground truth, other factions' internal reasoning, is available only to offline processes such as value function training and consolidation.

Without that split, `campaign_ai_log.txt` is a fog of war exploit wearing a learning hat.

### Valence has to be relative to expectation, not absolute

D8 says record whether the outcome was positive. Positive against what baseline?

Winning a battle you should have won easily, while taking heavy casualties, is a bad outcome. Losing a battle you were always going to lose, while extracting most of the army, is a good one. Absolute valence records the first as a success and the second as a failure, and teaches the agent the opposite of the truth.

So valence is measured against what was predicted. That makes the learning signal **prediction error**, not outcome.

### Weight and store by surprise

This follows directly and it is the single most useful principle here.

A battle that went exactly as predicted teaches nothing, and storing it adds noise and retrieval cost for no gain. A battle that went very differently from prediction is the one worth remembering, because it marks where the current model of the world is wrong.

Consequences:

- Each record carries the prediction, the outcome, and the gap
- Retrieval weights on the gap, not on whether it was a win
- Storage can be filtered by the gap, which bounds corpus growth without an arbitrary cap
- Failures and surprising successes are equally valuable, so the corpus does not become a highlight reel

This also makes D6 pay off twice, since a declared battle intent is a prediction, so the gap between intended and achieved result is a surprise measure that costs nothing extra to compute.

### Where the human learning analogy breaks, and the fix

**Humans generalise from few examples. Retrieval does not.** A person watching one battle extracts a principle. Retrieval stores an instance and matches on surface similarity, so without an abstraction step you accumulate thousands of instances and retrieve the wrong ones.

**Fix: a consolidation pass.** Periodically, offline, a process reads accumulated records and writes generalisations, which land in the doctrine layer from C8 as priors with confidence, and are then tested against outcomes like any other doctrine. The agent writes its own doctrine and the game grades it.

That is a real closing of the loop, and it is the part that makes this learning rather than accumulation. It also has a pleasing correspondence with the analogy, since consolidating experience into principle offline is roughly what sleep does.

**Humans forget, and that is a feature.** An append only corpus grows without bound, slows retrieval and fills with material from obsolete versions of the agent. Records need decay, deduplication, eviction, and a version tag so that experience generated by a much earlier agent can be aged out or down weighted.

**Correlation is not causation, and humans are bad at this too.** Here the system can beat the analogy rather than inherit its weakness, because prediction error gives a sharper signal than "I did this and won" ever does.

### What this changes elsewhere

- **C9's three layer memory stands**, with the experience corpus now fed by three sources rather than one, and weighted by surprise rather than by outcome.
- **D5 is unaffected and reinforced.** The game still measures. This only widens whose behaviour gets measured.
- **The value function gets a much larger training set**, drawn mostly from native AI play, which materially improves its feasibility.
- **Opponent modelling gets a human style model** as a side effect, which matters because D2 chose opponent as the agent's role.

## C11: where the strength actually comes from

Ranked by contribution to beating a competent human at Rome. The order is close to the inverse of how interesting each one is to build.

### 1. Being tireless and consistent

Almost certainly the largest single source of strength, and it requires no intelligence at all.

Total War campaigns are lost to accumulated neglect far more than to tactical inferiority. A human forgets a stack in the north, skips a build queue for six turns because the settlement is quiet, stops checking diplomacy around turn 90, misses that a rival's army composition changed. An agent that plays turn 180 with exactly the care it gave turn 3, checking every settlement, every queue, every border every turn, is formidable before it has had a single good idea.

This is cheap to build. It is mostly the observation channels plus a competent behaviour layer.

### 2. Battle micro at the freeze tick

The second largest, and also mechanical rather than clever.

Human battle skill degrades with unit count. Managing twenty units at once, pulling a wavering unit back before it breaks, timing a cavalry charge into an already engaged flank, keeping skirmishers alive while they retreat through gaps, is where human theoretical advantage evaporates in practice. An agent with `toggle_game_update` micros every unit on every tick without degradation.

**This is also the biggest fairness question in the design, and it is not the same one as fog.** Freezing is not seeing what a player cannot see, it is acting faster than a player can act. At a fast tick the agent is superhuman at micro in a way that has nothing to do with being smart. The tick rate is therefore a difficulty dial, and it deserves the same explicit treatment as the fog boundary.

An AI that out clicks you is a different experience from one that out thinks you. Worth deciding which you are building rather than discovering that the first arrived by default.

### 3. The learning apparatus

Real, and slower to pay off than 1 and 2. Four thousand faction turns per campaign is a genuine data advantage, but it converts to strength gradually and through the value function rather than immediately.

### 4. The LLM deliberation tier

Least contribution to raw strength, most contribution to the experience. This has been the consistent read since the architecture document and nothing since has changed it.

### Feeling formidable is not the same as being formidable

Human perception of an opponent's strength is driven by four things, none of which is playing optimally:

- **Does it punish my mistakes?** Responsiveness
- **Does it do things I did not expect?** Unpredictability
- **Does it appear to have a plan across many turns?** Coherence
- **Does it change approach when I counter it?** Adaptation

An agent that plays near optimally but predictably feels weaker to face than one that reads you and shifts. This is where the deliberation tier and the experience corpus earn their place: not in Elo, in dread.

### Design implication

Build the boring strength first, because it is cheap and it is most of the effect. Spend the expensive, interesting effort on coherence and adaptation, because that is the part that cannot be got any other way and it is what makes the opponent feel alive rather than merely difficult.

## C12: what unthrottled actually means

D9 removes the artificial limit. The real limit is elsewhere, and it changes where the engineering effort should go.

### The ceiling is actuation, not decision

A freeze cycle costs: `toggle_game_update`, `output_unit_positions`, read and parse, decide, issue orders, `toggle_game_update`. Only one of those is slow.

Issuing orders is synthetic input, and synthetic input has to move, dwell so the game registers hover state, then click. Estimated 100 to 300 ms per unit order. Twenty units is **2 to 6 seconds of pure actuation per tick**, before any deliberation.

So the floor on cycle time is set by clicking, not by thinking. **You cannot tick faster than you can click.**

### Wall clock is the real budget

Game time only advances when unfrozen, so the agent is not disadvantaged by taking wall clock. You are.

| Game time per tick | Ticks in a 20 minute battle | Wall clock at ~3s per cycle |
|---|---|---|
| 5s | 240 | ~12 min overhead, battle takes ~32 min |
| 2s | 600 | ~30 min overhead, battle takes ~50 min |
| 0.5s | 2,400 | ~2 hours overhead, battle takes 2.5 hours |

The tick rate is therefore bounded by your patience, not by the agent's capability. That is the honest reading of "as fast as it can be".

### So the way to go fast is to act less, not to click faster

Three levers, in order of payoff:

**1. Diff based actuation.** On most ticks most units are already doing the right thing. Compute the desired state, diff against the current state, and issue only the delta. Plausibly cuts actuation by 80 to 90 percent, and it is the single biggest win available.

**2. Batch orders.** Use unit groups rather than per unit sequences. Rome supports control groups, and the script layer has `unit_group_automate_attack`, `unit_group_automate_defend_position` and `unit_order_move_to_orientation`. One group order replaces many individual ones.

**3. Prefer script primitives over raw input where reachable.** `e_select_unit` and the group commands are more reliable and faster than synthesised clicks. Subject to the C8 caveat that the background script cannot take external input, so this depends on the signalling question in the integration document resolving well.

### Two things to keep

**Make the tick rate a config value, not a constant.** It costs nothing now and preserves the dial if you ever want difficulty levels, or if battles turn out to be a formality and you want them to breathe.

**Know what a "beats the vanilla AI" number means.** The shipped AI does not freeze. A win rate measured at full freeze rate is measuring micro, not judgement. Not a reason to throttle, just a reason not to read that number as evidence about the strategy layer.

### The prediction

At full speed the agent will be very hard to beat in battles, and its wins will come from execution rather than insight. The likely consequence is that the campaign layer becomes the interesting part, since battles stop being where the game is decided. That is a testable prediction rather than a warning, and if it turns out to make battles dull, the dial is right there.

## C13: where determinism lives

An audit, prompted by the original framing of LLM for reasoning plus deterministic models for prediction. That framing survived and most of the system is the deterministic half.

### The distinction D5 could be misread as forbidding

D5 says nobody authors what a good outcome is. It says nothing about authoring **what happens**.

- **Dynamics**, meaning given a state and an action, what state results, are authored from Feral's published formulae. Fully legitimate and fully deterministic.
- **Values**, meaning whether the resulting state is good, are learned from game measured outcomes.

**Deterministic dynamics, learned values.** That is the same shape as a game engine with a learned evaluator, and it is available here because Feral published the maths. The project does not have to learn physics, only preferences.

### The deterministic predictive models

These are what the original "deterministic models for predictions" meant, and they are better supported than assumed, because the formulae are documented rather than reverse engineered.

| Model | Predicts | Source |
|-------|----------|--------|
| Melee and charge resolution | Will this engagement win, and at what cost | `Battle_and_Campaign_Formulae.md`: charge bonuses, formation bonuses, fear effects, experience chevrons, general's bonuses |
| Fatigue and morale | Will this unit break, and when | Same |
| Auto resolve estimate | Fight it or auto resolve it | Same, plus observed outcomes |
| Siege duration | Turns to reduce a settlement | Documented siege turn calculations |
| Economy projection | Income, recruitment timing, upkeep headroom | Trade calculations, distance to capital penalty, `EDB` |
| Movement reachability | Where can this army be in N turns | `Campaign_Map_Pathfinding.md` |

### Full inventory by determinism class

| Class | Components |
|-------|-----------|
| **Analytical, rule based, no learning** | Behaviour and execution layer, actuation sequencing, diff based order computation, verification loops, belief decay bookkeeping, feasibility check on battle intent, safety layer, all the predictive models above |
| **Learned, deterministic at inference** | Value function, outcome predictor, opponent style model |
| **Stochastic but seeded, so reproducible** | Search rollouts, blunder policy, root temperature |
| **Non deterministic** | The LLM director and narrator only |

### How little of the system the LLM actually touches

By decision count rather than by importance:

| Context | Total decisions | LLM involved | Deterministic share |
|---|---|---|---|
| One battle | ~600 ticks | 10 to 20 deliberations | **>95%** |
| One campaign turn | 20 to 50 actions | 1 to 3 deliberations | **~90 to 95%** |

And zero percent of executions. Nothing the LLM produces moves a unit directly; it produces intent, and deterministic layers turn intent into orders.

### Reproducibility

Seeded search plus the logged directives from the intent record means a whole match replays exactly, despite one non deterministic component. That is a debugging property worth protecting, and it is the reason the directive log was worth keeping even after the harness was shelved.

## C14: D10 collapses the architecture from three tiers to two

The original design had reflex, search, and deliberation. D10 removes the middle one. What remains is a **two tier** system:

- **Deliberation**, the LLM, slow, produces multi step intent
- **Reactive**, fast, single step, consults the deterministic predictors from C13

The predictors are still built, since they were always separate from the rollout engine. They are consulted to compare candidate actions by predicted immediate outcome rather than to expand a tree.

### The good consequence: B5 evaporates

Bottleneck B5 was that model error compounds with rollout depth, so a 90 percent accurate per step model is 35 percent accurate at ten steps, making deep search in an approximate model confidently wrong.

**With no rollouts, error does not compound.** One step predictors only have to be right one step ahead, which is a far easier target and is exactly what Feral's published formulae give directly. B5 is moot and the accuracy bar drops substantially.

### The cost: no multi step tactical construction

Search is what finds plans the designer did not anticipate. Without it the agent will not spontaneously set up a three move encirclement, bait an overextension, or sequence a campaign manoeuvre across turns.

Two things carry that load instead:

**The deliberation tier.** The LLM supplies multi step structure as intent, and the reactive layer executes it one step at a time. This is the classic hierarchical arrangement and it works, with the caveat that a 12B class model is weak at multi step planning, which was already noted in B1b.

**Open proposal, for decision: plays.** Parameterised multi step patterns such as hammer and anvil, refused flank, feigned retreat, encircle left. The LLM selects a play, the reactive layer executes its steps. Not search, a playbook. It would give multi step coherence without a tree, and it fits D7 and D8 unusually well, since doctrine documents describe plays and the consolidator could write new ones. **Adopted 2026-09-01** — see `agent/reactive/plays.py`.

## C15: D11 and D12 create a write path AO does not currently have

The two answers compound, and together they need something Reach does not provide.

### The requirement

D11 puts both corpora on AO. D12 has the consolidator writing doctrine directly. Both mean data flowing **into** AO's knowledge base, and **Reach exposes no write path into the KB.** It is a read and run protocol.

Volume is not the problem. C10 estimated around four thousand faction turns per campaign, and at a few KB per record that is tens of megabytes over a campaign, trivial on a LAN.

### Options, none chosen

| Option | Shape | Note |
|--------|-------|------|
| Engine HTTP ingest endpoint | Add an ingest route to `orchestration.serve` | **Chosen 2026-09-01** — `POST /api/v1/kb/ingest` and `/upsert` over mTLS from Process B |
| Shared filesystem on `ada` | Host app writes files, a `rag_sources` entry reads them | Not used |
| Custom tool sandbox | Deploy a KB write tool through `ReachSandboxDeployClient` | Not used; `deploy_to_ao_sandbox: False` unchanged |
| Agent side write | An AO agent with a write tool stores what it is passed | Not used |

**Resolved 2026-09-01:** engine HTTP ingest over mTLS. Interim RAG split: ingest-time observable/privileged separation; host pre-injects observable context until `direct_agent` gains `rag_sources`.

### The boundary that changes, and the one that does not

"AO never writes" no longer holds. "AO never actuates the game" still does, and that is the boundary the kill switch depends on. Worth keeping the two separate in discussion, because they are easy to conflate.

### The good consequence: doctrine stops being baked in

The overlay design noted that skills are concatenated into agent backstory at pack time, so new doctrine only went live on a re-pack plus `refresh_overlay`.

With D11 putting doctrine in an AO corpus, it is **retrieved rather than baked**, so consolidator writes take effect immediately with no re-pack. That removes the operational awkwardness entirely. The skill mechanism is then only worth using for a small stable core, if at all.

### The observable and privileged split needs corpus level enforcement

C10 requires that privileged material, meaning `campaign_ai_log.txt` decisions and fog lifted ground truth, never reaches the agent at decision time. With both corpora on AO that has to be enforced by keeping them as **separate `rag_sources` ids**, with play loop agents granted only the observable one.

**To verify:** AO's `rag_ids` and the `rag_query` grant mechanism are documented on the planner path. Whether a `direct_agent` call can declare or be restricted to specific rag sources needs checking against the engine, because the entire play loop uses `direct_agent` rather than the planner. If it cannot, the split needs another mechanism.

### D12 sharpens an existing risk

The risk register already notes that D8 lets the agent discover exploits rather than only read about them. D12 removes the review point, so the agent can now discover an exploit, consolidate it into doctrine, and begin applying it without anyone seeing it.

The mitigation does not have to be a gate. Version every doctrine write, log it, and keep the outcome side degeneracy check, meaning flag any tactic that starts winning overwhelmingly and cheaply against varied opposition. That makes review retrospective rather than blocking, which preserves the closed loop D12 was chosen for.

## Risk register

| Risk | Driver | Mitigation |
|------|--------|------------|
| Abstraction fits neither layer | D2 plus D3 | Share reasoning only, per C3. Revisit if the shared surface starts growing plumbing |
| Belief model retrofitted rather than designed in | D4 | Contract carries provenance, age and confidence from the first version, per C1 |
| Silent actuation failures | D1 | The intent record in C5, if accepted |
| Information valuation never gets built, so the agent plays fogged but does not scout | D4 | Treat scouting as an action class in the planner from the start, per C2 |
| Portable contract built for a platform of one game | D3 | Second adapter, even a toy one, before the contract is declared stable |
| Patch breaks the actuation tier | D1 | Pin the game version, keep console text preferred over pixel interaction |
| Agent discovers exploits rather than reading about them, then writes them into its own doctrine unreviewed | D8 with D12 | Input side filtering cannot help and D12 removes the review point. Version and log every doctrine write, and keep the outcome side degeneracy check: flag any tactic winning overwhelmingly and cheaply against varied opposition. Review is retrospective rather than blocking |
| Agent is tactically shallow with no multi step construction | D10 | Deliberation tier carries multi step structure as intent. The plays proposal in C14 is the candidate mitigation, not yet decided |
| Privileged experience reaches a play loop agent through shared AO retrieval | D11 with C10 | Separate `rag_sources` ids for observable and privileged, with play loop agents granted only the observable one. Depends on `direct_agent` supporting rag source restriction, which is unverified |
| Privileged learning data leaks into decision time retrieval | D8 with D4 | Every record split into observable and privileged parts, only the observable part retrievable during play |
| Superhuman micro arrives by default and the agent out clicks rather than out thinks | D9 | Accepted deliberately. Keep tick rate as a config value so the dial survives |
| Battles take hours of wall clock to watch | D9 | Diff based actuation and batched group orders, per C12. The cost is yours, not the agent's |
