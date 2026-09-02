# Test campaign bootstrap

Grand Campaign on **monitor 2**, faction **Julii**, save slug **`comstar-julii`**.

After first bootstrap, update [`config/campaign.yaml`](../config/campaign.yaml):

```yaml
campaign:
  save_path: "<absolute path to .sav>"
  created_at: "<ISO8601>"
  game_version: "<pinned from Phase 0 spike>"
```

Launch: `scripts/launch_rome.ps1`
