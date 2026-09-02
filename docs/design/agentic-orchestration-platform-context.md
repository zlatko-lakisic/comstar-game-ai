# Platform context: agentic-orchestration + AO Reach

Reference notes for the Comstar Game AI project. Both repos were cloned and read on 2026-09-01.

- Engine / platform: https://github.com/zlatko-lakisic/agentic-orchestration (VERSION 2.7.0, Apache-2.0)
- Client SDK: https://github.com/zlatko-lakisic/agentic-orchestration-reach (VERSION 0.15.0, "AO Reach", package `ao_reach`)

## 1. What agentic-orchestration is

A model-agnostic, agent-based orchestration engine built on CrewAI. The thesis is a four part process loop rather than one smart model:

1. Coordinator that replans (`Planner`) - turns a goal plus session history into a JSON plan of steps, each naming an agent provider id and optional MCP and skill ids. `--dynamic-iterative` runs one step per round and replans after each result.
2. Execution with steps as a working record (`Runner` + tools) - builds a CrewAI Crew per step, resolves MCP configs and skills, feeds prior step output forward (`AGENTIC_STEP_CONTEXT_INJECT`).
3. Reevaluation mid run (`Adaptation`) - iterative mode closes the loop inside a single goal.
4. Knowledge transfer across tasks (memory and aggregation) - sessions on disk, optional SQLite FTS knowledge base, optional learning loop. Explicitly labeled partial today.

Plus an impartial QA gate (v1, on by default in advisory mode): harness assertions, judge score against an optional rubric, and a faithfulness review in one pass/fail report after finalization. `AGENTIC_IMPARTIAL_QA=0` disables; `AGENTIC_IMPARTIAL_QA_FAIL=1` makes it a hard gate.

### Monorepo layout

```
agentic-orchestration/
├── agentic-orchestration-tool/   Python engine, entry main.py
│   ├── config/workflows/         static workflow YAML
│   ├── config/agent_providers/   one YAML per agent template (dynamic catalog)
│   ├── config/mcp_providers/     MCP catalog (streamable_http or stdio)
│   ├── config/agent_skills/      procedural skills (markdown instructions)
│   ├── config/agent_harnesses/   platform verification profiles L0 to L3
│   ├── orchestration/            runner, planner, sessions, learning, KB
│   │   └── backends/             inprocess | subprocess | kubernetes
│   ├── deploy/k8s/               coordinator, warm pool, delegation broker, run-store PVC
│   └── docker/                   coordinator + worker images
├── agentic-orchestration-admin/  Angular admin UI (topology, access, catalogs, control)
├── agentic-orchestration-web/    Node WebSocket chat UI, spawns the Python tool
├── examples/verticals/           domain overlays: healthcare, logistics, society_research_panel
├── docs/                         GitHub Pages source, ~30 topic pages
└── site/, assets/, extras/, scripts/
```

Note: `agentic-orchestration-admin/out-tsc/` holds committed build output, roughly a thousand files. Ignore it when searching.

### Catalogs

- Agent providers: one YAML per entry. `type` is one of `ollama`, `openai`, `anthropic`, `huggingface`, `vllm`, `jetstream`. Entries can declare `hardware.architecture: [cpu|gpu|tpu]` and `min_vram_gb`; the planner filters out providers with no overlap against detected hardware. `AGENTIC_AVAILABLE_ARCHITECTURES`, `AGENTIC_ASSUME_GPU`, `AGENTIC_ASSUME_TPU` override detection.
- MCP providers: `streamable_http` (URL plus headers) or `stdio` (command, args, env). Shipped ids include `home_assistant`, `search_brave`, `search_tavily`, `search_exa`, `fetch_url`, `memory_knowledge_graph`, `filesystem_local`, `weather_mcp`. Entries carry `description`, `capabilities`, `good_for`, `planner_hint` and are credential gated.
- Agent skills: inject markdown instructions into task descriptions or agent backstory. They do not add callable tools; use MCP for that. Shipped ids: `echo_skill`, `release_process`, `pr_review`.
- Workflows: files under `config/workflows/` that declare both `meta` and `workflow` are offered to the Ollama router. `meta` carries `id`, `summary`, `description`, `good_for`, `router_include`.
- Extra catalog paths merge via `AGENTIC_EXTRA_AGENT_PROVIDERS_PATH`, `AGENTIC_EXTRA_MCP_PROVIDERS_PATH`, `AGENTIC_EXTRA_AGENT_SKILLS_PATH`.

### Agent provider lifecycle

`validate_config` -> `initialize` -> `health_check` -> `build_agent` -> `on_workflow_start` -> `before_task` -> `after_task` -> `on_workflow_end` -> `cleanup`. `reset`, `suspend`, `resume` exist but are not called by the runner. Custom providers register by subclassing `AgentProvider` with a `PROVIDER_TYPE` class attribute, or by pointing `provider_class` at an importable path.

### Execution backends

`AGENTIC_EXECUTION_BACKEND` selects `inprocess` (default), `subprocess` (per step workers on one machine), or `kubernetes`. In Kubernetes mode one workflow step maps to one worker execution (warm pool pod reuse or a one shot Job); crew agents for that step run in process inside the worker, not one pod per agent. Steps hand off through a shared run-store PVC at `{run_id}/{step_id}/result.json`.

Deployed components: `agentic-coordinator` (web UI, planner, dispatch), `agentic-engine` (`orchestration.serve` on port 8765, this is what Reach talks to), `agentic-warm-pool`, optional `agentic-delegation-broker`, Ollama (`managed_k8s`, `external`, or `managed_process`), run-store PVC, optional MCP gateway Deployments. Catalogs are bind mounted from the git checkout so catalog changes do not need image rebuilds.

Reference deployment is a Jetson AGX Orin on k3s, namespace `agentic-orchestration`, web UI on NodePort 30487 behind a reverse proxy.

### Configuration

Environment first. `agentic-orchestration-tool/.env.example` is the authoritative checklist. Categories: provider keys (`OPENAI_*`, `ANTHROPIC_*`, `HF_*`, `OLLAMA_HOST`), planner (`AGENTIC_PLANNER_MODEL`, `AGENTIC_PLANNER_USE_LITELLM`, `AGENTIC_PLANNER_MAX_STEPS`, retries, JSON mode), sessions, hardware, MCP, progress, learning and KB, answer cache, iterative mode, execution backends, and web server (`AGENTIC_WEB_HOST`, `AGENTIC_WEB_PORT`, in the web folder's own `.env`).

Runtime data is gitignored: `__orchestrator_sessions__`, `__orchestrator_learning__`, `__orchestrator_kb__`, `__orchestrator_mtls__`, `__output__`, `harness_runs`.

### Verification

- Platform agent harness: tiered per catalog checks, `--harness-agent`, `--harness-batch`, tiers L0 to L3, profiles in `config/agent_harnesses/`. L0 and L1 run in CI.
- User agent harnesses: domain scenario packs, `--harness-dir`, `--user-harness-run-all`. Healthcare example under `examples/verticals/healthcare/harnesses/`.

## 2. What AO Reach is

Client SDK for talking to a shared AO engine daemon from a desktop, workstation, or embedded app. Dart is the reference implementation (`lib/`), and there is a protocol compatible Python package under `python/` (used by HACS Comstar). It gives an app two things:

1. Ephemeral `client.*` agents registered for the session only, never mounted on the host.
2. Local tools (filesystem, OAuth MCPs, npx stdio servers) exposed to the engine over a WebSocket reverse tunnel, so no public port on the client machine.

Reach connects to the engine directly on port 8765, not through the web UI or the security gateway. Do not point Reach at the web UI NodePort.

### Engine requirements

- AO daemon v1.27.0 or later with `AGENTIC_SERVE_SESSION_OVERLAY=1`, plus `AGENTIC_SERVE_MCP_TUNNEL=1` when registering `tunnel://session-mcp/...` MCPs.
- Optional speech: AO 1.28.0 or later, `AGENTIC_SPEECH_ENABLED=1` plus sidecars.
- Optional mTLS: AO 1.29.0 or later.
- Optional streaming: `AGENTIC_SERVE_STREAM_STDOUT=1`, `AGENTIC_SERVE_STREAM_THOUGHTS=1`.
- Dart SDK ^3.5, Node `npx` for stdio MCPs, `openssl` on PATH for enrollment.

### Module map

| Module | Role |
|--------|------|
| `SessionBridge` | WebSocket lifecycle, overlay register and clear, tunnel responder, `direct_agent`, `chat` / `run_dynamic`, cancel, speech discovery |
| `ReachConnectionConfig` | base URL, required `app_id`, headers, TTL, run mode, session env, allowlists, mTLS, sandbox opt in |
| `OverlayPacker` | reads AO layout YAML from an overlay root into `client.*` agents plus MCP entries |
| `McpSessionSpec` | declares stdio tunnel vs hosted HTTP MCPs |
| `LocalMcpHost` | loopback `mcp-proxy` for stdio MCPs |
| `SessionMcpBootstrap` | app implemented protocol deciding which local MCPs to start; Reach stays product agnostic |
| `HybridSessionMcpBootstrap` | sandbox first with tunnel fallback |
| `ReachCatalogClient` | `GET /api/v1/catalog` for stock agents, MCPs, skills, harnesses plus `requiredSecrets` |
| `ReachMtlsEnroller` / `ReachMtlsConfig` | token enroll, persist `cert.pem` / `key.pem` / `ca.pem` |
| `ReachRunStatus` | streamed progress, phase, message, plus queue fields |
| `SpeechClient` | OpenAI compatible STT and TTS over HTTP to sidecars |
| `ReachToolPackager` / `ReachSandboxDeployClient` | custom tool wheel plus manifest bundle, upload and activate in an AO sandbox |

### Key call shapes (Python)

```python
config = ReachConnectionConfig(
    base_url="https://ao-host:8765",
    app_id="comstar-game",          # required, stable per app
    headers={"x-agentic-session-id": "sess-1"},
    ttl_seconds=3600,
    dynamic_planning=True,
    default_run_mode="dynamic",
    session_env={"OPENAI_API_KEY": ...},
    allowed_agent_provider_ids=["gpt_research"],
    allowed_mcp_provider_ids=["search_tavily"],
    allowed_skill_ids=["web_research"],
    mtls=ReachMtlsConfig(material_dir=...),
)

await bridge.start(config=config, overlay_root=..., mcp_bootstrap=...)

await bridge.direct_agent(agent_provider_id="client.my_agent", text=..., context="",
                          mcp_provider_ids=[...], images=[...], priority="high",
                          on_status=..., timeout=300.0)

await bridge.chat(text=..., run_mode="dynamic", selected_agent_provider_ids=[...],
                  session_id=..., images=[...], priority=..., on_status=..., timeout=600.0)

await bridge.cancel(question_id)   # cancels one tagged run, keeps the socket open
await bridge.stop()
```

Behaviors worth remembering:

- Overlay root must contain `agent_providers/*.yaml`. `OverlayPacker` rewrites each `id` to `client.<id>`, and for `type: ollama` it drops `ollama_host` and forces `selfcontained: false`.
- Empty or omitted `allowed_mcp_provider_ids` / `allowed_skill_ids` means the planner catalog is overlay `client.*` entries only, not the full stock catalog. Pin stock ids explicitly to opt in. This changed in Reach 0.13.0.
- Empty `allowed_agent_provider_ids` still means unrestricted for agents.
- Images: `[{mimeType, dataBase64, name?}]`, types `image/jpeg|png|webp|gif`, capped at 16 images, 4 MiB each, 20 MiB total. AO answers those turns with a vision model, plain text, no tool calls. Failures come back as `invalid_images`, `payload_too_large`, or `vision_unavailable`. Prefix text with `[model=gpt-4o-mini]` to pick a vision model.
- Cancellation needs a `questionId`; untagged busy runs cannot be cancelled.
- Priority is a named tier (`realtime`, `high`, ...) or 0 to 100, used for global execution queue admission. `ReachRunStatus` exposes `queuePhase`, `queuePosition`, `queueLength`, `queuePriority`, `elapsedMs`, `isQueued`, `isPreempted`.
- Errors raise `ReachRunException` / `ReachRunError` carrying a `code`.
- Mock client profiles for e2e smoke: `mock-comstar`, `mock-continue`, `mock-ha`, via `python/ao_reach/mock_client_runner.py`.

### mTLS trust model

One time enrollment: an admin mints a token, Reach generates a key and CSR with `openssl`, posts to `POST /api/v1/mtls/enroll`, and persists `cert.pem`, `key.pem`, `ca.pem`. Steady state uses `https` and `wss` with the client cert; identity comes from the cert SAN or CN rather than headers. Enroll tokens are short lived; client certs default to 365 days. Public endpoints with server TLS only: `/health`, `/api/ping`, `/api/v1/mtls/ca`, `/api/v1/mtls/enroll`. Everything else including `/ws` requires a verified client cert when `AGENTIC_SERVE_TLS_REQUIRE_CLIENT_CERT=1`.

Single client revoke without rotating the CA: admin UI under Access -> mTLS clients, or `python -m orchestration.serve.mtls revoke-client --cn <name>`. Deny list lives in `__orchestrator_mtls__/revoked.json`.

Known gaps: speech sidecars are cleartext HTTP, there is no automatic cert renewal, and server certs need IP SAN entries for any IP based URL a client dials.

### Custom tool sandbox contract (v1, Reach 0.14.0)

`CustomToolManifest` carries `contractVersion`, `toolId`, `toolVersion`, `runtime`, `wheel`, `entrypoints`, `requiredEnv`, `permissions` (filesystem paths, network bool, env keys), `healthcheck` (path, timeout), and `fallbackPolicy` (default `tunnel`). `ReachToolPackager` builds a wheel plus manifest zip; `ReachSandboxDeployClient` uploads and activates it; `HybridSessionMcpBootstrap` tries the sandbox first and falls back to the tunnel. Opt in with `deploy_to_ao_sandbox` (default false). On successful sandbox activation Reach does not append loopback MCP entries to the overlay register; AO merges activated tools server side.

## 3. Notes for building on this

- The app owns `SessionMcpBootstrap`. Reach deliberately knows nothing about the product's tools.
- Pin the Reach git ref to a tag (`vX.Y.Z`); tags are the published artifact.
- Overlay agents are per session and disappear when the bridge stops, so no host catalog changes are needed to ship new client agents.
- For a new vertical on the engine side, the pattern is `examples/verticals/<id>/` with orchestrator context, extra agent provider YAML, optional MCP YAML, optional harness pack, and web start scripts, wired into `orchestration/example_overlays.py` and `main.py --example` choices.
- Local clone locations in this session: `/home/claude/projects/agentic-orchestration` and `/home/claude/projects/agentic-orchestration-reach`.
