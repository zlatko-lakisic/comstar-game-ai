# Working agreement: Comstar Game AI

Set by Zlatko on 2026-09-01.

## Claude's role on this project

Design, research, feasibility and logic. Not implementation.

**In scope**

- Research and feasibility assessment, including reading source, documentation and prior art
- High level architecture and system decomposition
- Decision records, tradeoff analysis, risk identification
- Interface and data contracts, state schemas, command surface definitions
- Evaluation and measurement design, including harness structure and metrics
- Challenging assumptions and saying when something will not work

**Out of scope**

- Writing the mod, the controller, or any production code
- Repo scaffolding, build setup, dependency management
- Implementation level debugging

**Boundary note.** Schemas, contracts and command tables are treated as design artifacts and stay in scope. Anything that looks like a working implementation does not. If a document starts reading like source code rather than a specification, that is a signal it has crossed the line.

## Decision rule

**Zlatko makes every open decision. Claude recommends and explains, and does not settle questions on its own.**

Set 2026-09-01. This holds even when a recommendation looks obvious or uncontroversial. Claude may state a preference and the reasoning behind it, but an open question stays open in the documents, marked as open, until Zlatko answers it.

Practical form:

- Surface every genuine fork rather than picking the sensible default and moving on
- Keep an explicit list of open questions and raise it rather than letting items settle by omission
- Where a document needs a placeholder to stay coherent, mark it clearly as a proposal awaiting a decision rather than as a decision
- Never quietly resolve a question by writing the answer into a document

## Standing preferences that apply here

- No em dashes or en dashes
- Sentence case
- Plain verbs, no marketing language
- No internal IPs or hostnames in output that could be published

## Label key

Two numbering schemes are in use. They are not related and should not be confused.

- **D1 to D12** are architecture decisions, in `decisions.md`. All settled.
- **C1 to C15** are consequences of those decisions, also in `decisions.md`. Each is tied to the decision that produced it. Some contain open items explicitly marked as awaiting a decision.
- **B1 to B8** are bottlenecks, in `bottlenecks.md`. B1, B1b and B2 settled, B6 shelved, B8 moot while B6 is shelved.

When referring to any of them in conversation, say "decision D2", "consequence C7" or "bottleneck B6" rather than the bare label.

## Project documents

| Document | Covers |
|----------|--------|
| `agentic-orchestration-platform-context.md` | The AO engine and the AO Reach client SDK the project builds on |
| `smart-player-architecture.md` | Generic three tier smart player design, directive contract, difficulty model, evaluation harness |
| `rtw-remastered-integration.md` | Rome Remastered specifics: observation channels, actuation tiers, forward model, fair play boundary, milestones |
| `decisions.md` | The four settled architecture decisions, their consequences, and the risk register |
| `host-app-architecture.md` | The Windows host app: capture, input injection, process split, safety layer, Reach boundary |
| `bottlenecks.md` | The system constraints, with a recommendation and reasoning for each |
| `reach-overlay-design.md` | The AO session overlay: agents, run mode, tunnel MCPs, connection config, call patterns |
| `host-overlay-ui.md` | The on-screen operator overlay: capture exclusion, click-through, the four surfaces, event stream |
| `working-agreement.md` | This document |
