# ada model selection

Survey ada GPU and pin model for overlay agents.

- Hardware: NVIDIA RTX 4000 Ada (~20 GB VRAM)
- Default overlay model in YAML: `llama3.1:8b` until SSH survey updates this file

Run on ada:

```bash
nvidia-smi
ollama list  # if applicable
```

Update `overlay/agent_providers/*.yaml` `model:` field and `config/default.yaml` `ao.model` after survey.
