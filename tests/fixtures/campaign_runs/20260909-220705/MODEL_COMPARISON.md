# F6 model comparison — Segesta fixture

Temperature 0. Target: `besiege` with `target: set_segesta`.

## §6 shipping choice

**`phi4:14b`** (user decision 2026-09-10). Hold floor: **reask**.

| Model | Correct / N | Notes |
|---|---|---|
| `phi4:14b` | 0 / 10 | hold/; hold/; hold/; hold/; hold/ |
| `qwen2.5:7b` (local earlier) | 0 / 3 | hold |
| `llama3.1:8b` (fixture run) | 0 / 6 | always hold in deliberate log |

AO `direct_ollama` now forwards `temperature`/`num_ctx`. Engine restarted on ada; model pulled.
