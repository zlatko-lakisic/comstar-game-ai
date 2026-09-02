# Phase 0 environment spikes
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

$outDir = "docs\spikes"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

Write-Host "=== Display monitors ==="
python -c @"
from comstar_game_ai.game_io.display.monitors import list_monitors
import json
mons = [m.__dict__ for m in list_monitors()]
print(json.dumps(mons, indent=2))
open('docs/spikes/display.json','w').write(json.dumps(mons, indent=2))
"@

Write-Host "=== Windows build / preconditions ==="
python -c @"
from comstar_game_ai.game_io.preconditions import check_preconditions, check_windows_build
import json
ok, msg = check_windows_build()
pre = check_preconditions(require_game=False)
open('docs/spikes/preconditions.json','w').write(json.dumps({'build': msg, 'pre': pre.__dict__}, indent=2))
print(msg, pre)
"@

Write-Host "=== Game window ==="
python -c @"
from comstar_game_ai.game_io.window import find_game_window
from comstar_game_ai.shared.config import load_config
cfg = load_config()
w = find_game_window(cfg['game']['window_title_substrings'])
print('found' if w else 'not found', w)
"@

Write-Host "Spike output written to docs/spikes/"
Write-Host ""
Write-Host "Console output spike: with Rome on campaign map, run:"
Write-Host "  python scripts/run_phase1_observation.py"
Write-Host "Then grep message_log.txt for list_characters output."
Write-Host "If only in-game console pane, console queries need OCR or script telemetry instead."
