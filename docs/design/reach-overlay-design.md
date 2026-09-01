# Reach overlay design

What the host app registers with AO on `session_overlay_register`, and how each agent is called. Written 2026-09-01 against Reach v0.15.0 and the cloned `OverlayPacker`.

Companion to `host-app-architecture.md` and `decisions.md`.

## 1. Run mode: `direct_agent` in the loop, `dynamic` offline

**The play loop uses `direct_agent`. Not `chat`, and not dynamic planning.**

AO's dynamic planner exists to decompose an open ended goal into steps when the steps are not known in advance. The play loop task is not open ended: given this brief, produce this directive. One typed transformation with a known shape.

Using the planner anyway costs a planner call before any work starts, then a call per step, turning a 6 to 9 second directive into 30 to 90 seconds on the local model. It also makes the output contract less predictable, because the plan shape varies, and it lets the planner select agents and MCPs that were not intended. The benefit is zero, because the plan is already known.

`dynamic-iterative` adds a controller round per step and runs to minutes. Unusable inside a battle, and unnecessary on a campaign turn.

**Where dynamic earns its place is offline, where the task genuinely is open ended and latency is free.**

| Agent | Mode | Why |
|-------|------|-----|
| `battle_director` | `direct_agent` | Terse directive, 6 to 9s budget |
| `campaign_director` | `direct_agent` | Known transformation, reasoning mode, still one step |
| `opponent_modeler` | `direct_agent` | One analysis, lower cadence |
| `narrator` | `direct_agent` | Tiny output, realtime priority |
| `consolidator` | `chat`, `dynamic` | Read many records, find patterns, write generalisations. Genuinely multi step |
| `doctrine_ingestor` | `chat`, `dynamic` | Fetch, assess, triage, structure, tag |
| `post_mortem` | `chat`, `dynamic-iterative` | The one honest use for iterative: keep digging until the campaign loss is explained. Minutes are fine |

Config follows: set `dynamic_planning: False` and `default_run_mode: "dynamic"`, so the sticky default never routes a play loop call through the planner, and an explicit `chat` call gets dynamic unless it asks for iterative.

## 2. Overlay layout on disk

The packer requires `agent_providers/` and optionally reads `agent_skills/`. Skill `content.file` paths resolve relative to the skill YAML and are inlined with YAML frontmatter stripped.

```
overlay/
├── agent_providers/
│   ├── battle_director.yaml        -> client.battle_director
│   ├── campaign_director.yaml      -> client.campaign_director
│   ├── opponent_modeler.yaml       -> client.opponent_modeler
│   ├── narrator.yaml               -> client.narrator
│   ├── consolidator.yaml           -> client.consolidator
│   ├── doctrine_ingestor.yaml      -> client.doctrine_ingestor
│   └── post_mortem.yaml            -> client.post_mortem
└── agent_skills/
    ├── battle_doctrine.yaml        -> client.battle_doctrine
    ├── battle_doctrine.md          (content.file)
    ├── campaign_doctrine.yaml      -> client.campaign_doctrine
    └── campaign_doctrine.md
```

All seven agents point at the same model on `ada`. They differ by role, goal, backstory, attached skills, and output contract. That is exactly what the provider catalog is for, and it costs nothing extra to run.

Note the packer's Ollama handling: for `type: ollama` it drops `ollama_host` and forces `selfcontained: false`, so the engine's own Ollama configuration wins. If the model is served through vLLM instead, use `type: vllm` and let the engine hold the base URL.

## 3. The skills are baked into backstory at pack time

Worth knowing because it has a budget and an operational consequence.

When an agent YAML carries `skills: [battle_doctrine]`, the packer resolves it, rewrites the id to `client.battle_doctrine`, **and concatenates the skill body into that agent's `backstory`** under a heading. So the doctrine text is not retrieved per call, it is part of the agent definition.

Two consequences:

**Budget.** Doctrine text costs prefill on every single call for that agent. Bottleneck B1b already has prefill at 4,000 to 10,000 tokens with composed views. Keep always on doctrine short and bound it with `inject.max_chars`. Anything long belongs in retrieval, not in a skill.

**Update path.** New doctrine only takes effect when the overlay is packed and registered again. So the consolidation pass from C10 writes to the skill markdown files, and the host app re-packs and calls `refresh_overlay` to make it live. Consolidation is naturally a between sessions activity, which suits it.

## 4. Tunnel MCPs, read only

Two, both exposed by the host app through `SessionMcpBootstrap` and `LocalMcpHost`, registered as `tunnel://session-mcp/<alias>`.

| MCP | Tools | Purpose |
|-----|-------|---------|
| `client.game_query` | `get_army`, `get_settlement`, `get_history(n)`, `get_faction_belief(faction)`, `explain_unit(type)` | Pull detail the composed brief omitted, so the brief stays inside budget |

`client.experience` was removed by D11. Experience retrieval now happens AO side through `rag_sources`, so only one tunnel MCP remains.

**There is deliberately no act tool. AO never actuates.** The tunnel is read only, the directive comes back as the run result, and the host app decides what to do with it. That keeps every path to the mouse and keyboard inside the process that owns the kill switch, which is a safety property worth stating explicitly rather than leaving implicit.

`client.game_query` must respect the fog boundary from D4 and the observable/privileged split from C10. It serves belief, not ground truth.

## 5. Where the corpora live

**Decided 2026-09-01 by D11: both corpora live on AO** as `rag_sources` entries. All retrieval uses AO's machinery, so the `embedding` and `hybrid` backends and the citation grounding check apply throughout.

Consequences, detailed in `decisions.md` C15:

- **A write path into AO's knowledge base is required, and Reach does not have one.** Four candidate mechanisms are listed in C15 and none is chosen yet. This is the largest open item in this document.
- **`client.experience` is no longer needed as a tunnel MCP**, since retrieval happens AO side. The tunnel keeps `client.game_query` only.
- **Doctrine is retrieved rather than baked into backstory**, which removes the re-pack and `refresh_overlay` step that section 3 describes. The skill mechanism is then only worth using for a small stable core, if at all.
- **The observable and privileged split from C10 must be enforced as separate `rag_sources` ids**, with play loop agents granted only the observable one. Whether `direct_agent` supports restricting rag sources is unverified and needs checking against the engine, since the whole play loop uses `direct_agent` rather than the planner.
- **`deploy_to_ao_sandbox: False` in section 6 may need revisiting** if the custom tool sandbox turns out to be the chosen write path.

## 6. Connection config

| Field | Value | Reason |
|-------|-------|--------|
| `app_id` | `comstar-game-ai` | Stable across sessions, and AO Admin can hold per app prefs against it |
| `base_url` | The engine on `ada` | Co-located with the model, per C12 |
| `mtls` | `ReachMtlsConfig(material_dir=...)` | Cross machine, so enrol once and persist |
| `ttl_seconds` | 3600 | With TTL auto refresh for longer campaigns |
| `dynamic_planning` | `False` | Play loop uses `direct_agent` |
| `default_run_mode` | `dynamic` | Applies only when `chat` is called explicitly |
| `allowed_agent_provider_ids` | The seven `client.*` ids | Empty means unrestricted for agents, which is not what is wanted |
| `allowed_mcp_provider_ids` | `[]` | Since Reach 0.13.0 empty means overlay entries only, which is exactly right here |
| `allowed_skill_ids` | `[]` | Same |
| `session_env` | Empty | The model is local to the engine, so no provider keys cross the wire |
| `deploy_to_ao_sandbox` | `False` | Tunnel is sufficient, and the host app must stay the only actuator |
| `question_id_prefix` | `cga` | Per call ids encode context, see below |

## 7. Call patterns

| Context | Agent | Priority | Timeout | Question id | Cancel on |
|---------|-------|----------|---------|-------------|-----------|
| Battle event | `battle_director` | `high` | 20s | `btl-<battle>-<tick>` | Situation moves on before it lands |
| Battle floor tick | `battle_director` | `high` | 20s | `btlf-<battle>-<tick>` | Superseded by an event call |
| Campaign turn | `campaign_director` | `high` | 90s | `cmp-<turn>` | Turn ends |
| Every N turns | `opponent_modeler` | default | 120s | `opp-<faction>-<turn>` | Rarely |
| After any resolved action | `narrator` | `realtime` | 15s | `nar-<seq>` | Freely, it is cosmetic |
| Between sessions | `consolidator` | default | none | `con-<batch>` | Never |
| On ingest | `doctrine_ingestor` | default | none | `doc-<source>` | Never |
| Campaign end | `post_mortem` | default | none | `pm-<campaign>` | Never |

Every call carries an explicit `question_id`, because `cancel` requires a tagged run and untagged busy runs cannot be cancelled. Every timeout and every `ReachRunError` resolves to the neutral directive, and a move is never blocked on AO.

## 8. What is deliberately not in the overlay

- **No act or command tool.** Actuation stays entirely in the host app.
- **No stock MCP ids pinned.** The agents need no web search, filesystem or email. Empty MCP and skill allowlists give overlay-only catalogs, which is the desired isolation.
- **No filesystem MCP**, despite the packer offering it. The agents have no business reading the disk.
- **No speech.** Nothing here needs STT or TTS.
- **No sandbox deploy.** The custom tool sandbox would put agent reachable tools on the engine side, which conflicts with the host app being the sole actuator.

## 9. Open questions

- Does the campaign directive need `client.game_query` at all, or does a composed brief plus the experience MCP cover it? Fewer tool round trips is materially faster on a local model.
- Should `opponent_modeler` be folded into `campaign_director` to save a call, at the cost of a larger prompt and a mixed output contract?
- Does the consolidator need write access to the skill markdown, or does it return proposed doctrine for the host app to write? The second is safer and keeps AO read only end to end, which is consistent with everything else here.
