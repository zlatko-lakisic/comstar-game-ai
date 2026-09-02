# Comstar Game AI: smart player architecture

Design decisions for a reusable AI opponent platform. Target: turn based games with a forward model, AI plays as opponent, architecture is the deliverable and specific games are proving grounds.

Status: proposed, not yet built. Written 2026-09-01.

## 1. The core decision

Three tiers, and the LLM sits outside the control loop.

| Tier | Budget | What it does | Implementation |
|------|--------|--------------|----------------|
| Search | 10ms to 1s | Picks the move | MCTS over the forward model, game agnostic |
| Evaluation | per node | Scores positions | Learned from game measured outcomes, never authored. See D5 |
| Deliberation | seconds, off the critical path | Sets the objective, reads the opponent, talks | LLM via AO Reach |

Search carries playing strength. The LLM never picks a move and never removes a legal move from consideration. It shapes the objective function and the search priors, and it does the talking.

The evidence for putting strength in search rather than in the model: DeepMind's [Mastering board games by external and internal planning with language models](https://arxiv.org/abs/2412.12119) trained a transformer to act as world model, value function and policy, then measured what search added on top. At 1,000 MCTS simulations the system reached roughly 3,157 external Elo in chess, and even 100 simulations added 68 Elo over the model alone, scaling logarithmically with simulation count. The search is where the strength lives. That paper trains its own model; this project does not, which makes the point stronger, not weaker. A general purpose LLM asked to pick moves will be far below a modest search.

The precedent for the split itself is Meta's Cicero in Diplomacy: a planning engine chose the strategic intent, and a language model conditioned on that intent produced the dialogue. The language model never selected actions.

## 2. What the LLM is actually for

Be honest about this up front, because it changes what counts as success.

In a perfect information game with a decent evaluator, the deliberation tier will most likely **cost** Elo, not add it. What it buys is:

- **Legibility.** The opponent says what it is doing, and the move it plays matches what it said.
- **Character.** Posture, grudges, bluffing, a recognizable style that persists across a match.
- **Adaptation.** Reading a specific human's tendencies from play history and chat, and shifting the objective accordingly. This is the one capability that search alone does not have, and it pays off most in imperfect information games.
- **Difficulty that does not feel thrown.** A weaker setting that plays a coherent bad plan reads better than one that plays strong moves with random blunders.

So the platform has to measure the Elo cost of the deliberation tier rather than assume it away. See section 7.

## 3. Contract 1: the game adapter

The only mandatory per game code. Deliberately shaped like the [OpenSpiel](https://github.com/google-deepmind/open_spiel) state API (C++ core with Python bindings, actively maintained, ships MCTS, CFR and AlphaZero implementations), so that an `OpenSpielAdapter` is a thin shim and the platform gets chess, Go, Connect Four, Hex, Hanabi, Leduc poker and backgammon as test beds on day one. That is what turns "reusable platform" into a claim the harness can test rather than an assertion.

```python
Action = int

class GameAdapter(Protocol):
    game_id: str
    num_players: int

    # forward model, must be pure and cheap
    def initial_state(self) -> State: ...
    def legal_actions(self, s: State) -> Sequence[Action]: ...
    def apply(self, s: State, a: Action) -> State: ...
    def is_terminal(self, s: State) -> bool: ...
    def returns(self, s: State) -> Sequence[float]: ...
    def current_player(self, s: State) -> int: ...

    # naming, for logs and for the LLM
    def action_name(self, s: State, a: Action) -> str: ...
    def parse_action(self, s: State, name: str) -> Action | None: ...

    # seam to the deliberation tier
    def brief(self, s: State, player: int) -> StateBrief: ...

    # seam to the evaluator
    def features(self, s: State, player: int) -> FeatureVector: ...

    # D5: outcome signals the game itself computes, not authored scores
    def outcome_measures(self, s: State, player: int) -> Mapping[str, float]: ...
    def terminal_result(self, s: State, player: int) -> float | None: ...
```

`apply` must be pure. If the engine mutates in place, the adapter owns copying. Everything above `apply` assumes it can roll out a thousand times without touching real game state.

**`brief` is the hardest and most important method in the project.** It produces the compact, faithful, token cheap view the LLM reasons over. Give it a hard token budget (start at 800) and enforce it in a test. If the brief is too big, deliberation gets slow and expensive; if it is unfaithful, the LLM's advice is confidently wrong. Everything else here is plumbing by comparison.

## 4. Contract 2: the directive

What the deliberation tier returns. Game agnostic on purpose.

> **Amended 2026-09-01 by decision D5.** `objective_weights` over authored evaluation terms is removed. Nobody writes down what a good position is worth; the game's own outcome measures decide. The directive now expresses a preference over that outcome space rather than redefining it. See `decisions.md` C6.

> **Amended 2026-09-01 by decision D6.** `posture` is replaced by a declared target outcome. Aggression is derived from the target rather than set directly. See `decisions.md` C7.

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
  "focus_actions": ["e4", "Nf3"],
  "avoid_actions": [],
  "opponent_read": { "style": "...", "predicted_plan": "...", "confidence": 0.7 },
  "commentary": "one line, in character",
  "valid_for_plies": 4
}
```

How it is applied, and these rules are the safety model:

- `horizon` sets the discount rate over outcomes the game measures. `risk_posture` runs from -1 risk averse to +1 risk seeking and sets variance preference over the same outcome distribution. Neither changes what counts as a good outcome, only which good outcomes are preferred and when.
- `focus_actions` add bounded prior mass at the **root only**, in the PUCT prior. Cap the total contribution so search can always overrule it.
- `avoid_actions` reduce prior mass but never to zero.
- **Search never loses access to a legal move.** No filtering, no pruning by the LLM. This one rule is what makes the tier safe to ship.
- `valid_for_plies` expires the directive. Past expiry, fall back to the neutral directive.
- Malformed, late or missing response means neutral directive, log it, keep playing. A move is never blocked on the LLM.

Worst case degradation is that the AI plays pure search, which is the strong configuration anyway.

## 5. Contract 3: difficulty

Difficulty is a deterministic knob and not the LLM's job. Three parameters, all reproducible:

- **Search budget**, in simulations or wall clock.
- **Root temperature** over visit counts. Higher temperature means more variety and weaker play.
- **Blunder policy**: with probability epsilon, play the Nth best root action rather than the best. Bounded severity, never uniform random. A bad plan beats a random twitch for believability.

Persona comes from the LLM. Strength comes from these three numbers. Keeping them separate is what makes "friendly sparring partner" and "monster" the same codebase.

## 6. Timing and the AO Reach wiring

Turn based is a gift here: the deliberation call runs during the human's turn, which is free wall clock.

```
human turn starts
  -> fire client.narrator  (priority realtime)  for the move just played
  -> fire client.director  (priority high)      with brief(state, ai_player)
human plays
  -> if the director call has not landed and the state has moved on, cancel(questionId)
AI turn
  -> take the latest directive that is still within valid_for_plies, else neutral
  -> run search under a wall clock budget
  -> play
```

Reach specifics, checked against the cloned SDK at v0.15.0:

- One session overlay per match. `overlay_root/agent_providers/` holds `director.yaml`, `narrator.yaml`, `opponent_modeler.yaml`, which `OverlayPacker` rewrites to `client.director`, `client.narrator`, `client.opponent_modeler`.
- `app_id` is `comstar-game-ai`, stable across matches.
- `ttl_seconds` covers expected match length, with `refresh_overlay` for longer sessions.
- Pin stock catalog ids explicitly in `allowed_mcp_provider_ids` and `allowed_skill_ids`. Since Reach 0.13.0 an empty allowlist means the planner sees overlay `client.*` entries only, which is the behavior we want by default but should be chosen rather than inherited.
- Use `direct_agent`, not `chat`. The director returns one typed object; it does not need AO's multi step planner, and skipping it saves seconds.
- `priority` is a named tier or 0 to 100 and feeds AO's global execution queue. Narrator gets `realtime`, director `high`, opponent modeler default.
- `cancel(question_id)` for stale runs. It needs a tagged `questionId`, so always pass one.
- Expose a `client.game_query` MCP over the reverse tunnel via a custom `SessionMcpBootstrap`, with tools like `get_history(n)`, `get_opponent_stats()`, `explain_action(a)`. This keeps `brief` small and lets the agent pull detail only when it wants it.
- Errors arrive as `ReachRunError` in Python (`ReachRunException` in Dart), carrying `code`, `question_id` and `run_id`. A missed deadline raises plain `TimeoutError` instead. Catch both and treat them as "neutral directive" rather than as an exception path in the game loop.

**Reproducibility.** Log every deliberation call as `{questionId, ply, brief_hash, raw_response, parsed_directive, latency_ms}`. Seeded search plus a directive log makes any match exactly replayable even though the LLM is not deterministic. Without this the harness in the next section cannot work.

## 7. The harness, and why it is not optional

The failure mode of this project is that the deliberation tier makes the AI weaker while making it feel smarter, and nobody notices for six months. The harness is the defense.

Round robin self play, seeded, N games per pairing, per adapter. Arms:

1. `search-only` at fixed budget
2. `search + directive`
3. `search + directive + opponent-model`
4. `llm-only`, as a floor rather than a candidate

Report per adapter:

- **Elo** from the round robin. The number that matters is arm 2 minus arm 1. If it is negative, that is the price of personality, and it should be a recorded, deliberate number rather than a surprise.
- **Mean nodes per move** and **mean directive latency**, to catch the case where the tier is only winning because it got more wall clock.
- **Legibility rate**: fraction of moves where the played action appears in the directive's `focus_actions`. A cheap and surprisingly good proxy for "does this opponent feel coherent." Optimizing Elo and legibility together is the actual research question in this project.

This maps onto AO's user harness concept, so the packs can live under `harnesses/` and run through `--harness-dir` alongside the platform's own harnesses.

> **Amended 2026-09-01.** The target game is Total War: Rome Remastered, which exposes no forward model, so section 3's `apply` comes from an abstract simulator built on Feral's published formulae rather than from the game. See `rtw-remastered-integration.md`. Sections 4, 5 and 7 stand unchanged.

## 8. Proving grounds, in order

1. **Connect Four.** Trivial adapter, fast rollouts, human legible commentary. Purpose is to wire the seams, not to demo. Expect the directive tier to cost Elo here, because search dominates a small perfect information game completely.
2. **Leduc or limit poker.** Hidden information, where opponent modeling has real measurable value. This is the first arm where `search + directive + opponent-model` can plausibly beat `search-only`, and it is the honest demo.
3. **The real game.** Whichever title this is ultimately for.

Deliberately not chess first. The adapter is easy but the evaluator is a research project of its own, and iteration is slow.

## 9. Repository shape

```
comstar-game-ai/
├── core/
│   ├── contracts.py         GameAdapter, StateBrief, Directive
│   ├── search/mcts.py       game agnostic PUCT search
│   ├── eval/                heuristic and learned evaluators
│   └── difficulty.py        budget, temperature, blunder policy
├── deliberation/
│   ├── bridge.py            AO Reach SessionBridge lifecycle
│   ├── director.py          brief -> Directive, with neutral fallback
│   ├── narrator.py
│   └── bootstrap.py         SessionMcpBootstrap exposing client.game_query
├── adapters/
│   ├── openspiel.py         shim, unlocks the test bed games
│   └── <game>.py
├── overlay/agent_providers/ director.yaml, narrator.yaml, opponent_modeler.yaml
├── harness/                 arms, Elo round robin, legibility metric
└── replay/                  directive logs, seeded replays
```

## 10. Open questions

- Which title is the eventual target, and does its engine already expose a pure `apply`, or does the adapter have to fake one by copy and replay?
- Build on OpenSpiel directly, or reimplement the interface and keep OpenSpiel as a dev only dependency for the test beds? Second option is more work but avoids a C++ build in the game's runtime.
- Where does the game process run relative to the AO engine? Same host, edge device, or across a network? This sets the realistic deliberation latency and therefore how many plies a directive has to stay valid for.
- Does the human talk to the AI in natural language, or is the deliberation tier one directional? Two directional turns the opponent modeler into the most valuable component in the system.

## Sources

- [Mastering board games by external and internal planning with language models](https://arxiv.org/abs/2412.12119)
- [google-deepmind/open_spiel](https://github.com/google-deepmind/open_spiel)
- [OpenSpiel API reference](https://github.com/google-deepmind/open_spiel/blob/master/docs/api_reference.md)
