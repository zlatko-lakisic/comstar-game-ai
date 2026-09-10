# F6 model comparison — Segesta fixture

Temperature 0. Target: `besiege` with `target: set_segesta`.

## Partial local run (this workstation)

Only models present on local Ollama. The 20GB-card candidates in the handoff were **not** pulled here; `.cursor/secrets` is absent so ada SSH was not available.

| Model | Correct / N | Notes |
|---|---|---|
| `qwen2.5:7b` | 0 / 3 | hold / hold / hold |
| `llama3.1:8b` | 0 / 3 | not installed locally (HTTP 404) |

## Full matrix (run on ada)

```bash
python scripts/replay_director_models.py --samples 10
```

Candidates from the handoff: `qwen3.6:27b`, `gemma4:26b`, `qwen3.5:27b`, `phi4:14b`, plus small fallbacks `qwen3.5:9b`, `ministral-3:8b`, and incumbent `llama3.1:8b`.

Shipping choice is **section 6** — do not pin the overlay from this table alone.
