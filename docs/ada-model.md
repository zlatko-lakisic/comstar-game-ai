# ada model selection

Survey ada GPU and pin model for overlay agents.

- Hardware: NVIDIA RTX 4000 Ada (~20 GB VRAM)
- Default overlay model: **`phi4:14b`** (always-hold F6 / §6, 2026-09-10)

Run on ada before the next live campaign:

```bash
nvidia-smi
ollama pull phi4:14b
ollama list
```

Pinned in:

- `overlay/agent_providers/campaign_director.yaml` (`model: phi4:14b`)
- `config/default.yaml` (`ao.model: phi4:14b`)

Other agents still share this host model unless overridden per YAML. Refresh the Reach overlay after changing provider YAML.
