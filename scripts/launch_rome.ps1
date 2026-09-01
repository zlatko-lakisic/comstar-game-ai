# Launch Rome Remastered on monitor 2 via Steam
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

$cfg = Get-Content "config\default.yaml" -Raw
$appId = 885970
if ($cfg -match "steam_app_id:\s*(\d+)") { $appId = [int]$Matches[1] }

$steam = (Get-ItemProperty "HKCU:\Software\Valve\Steam" -ErrorAction SilentlyContinue).SteamPath
if (-not $steam) {
    Write-Error "Steam not found in registry"
}
$steamExe = Join-Path $steam "steam.exe"
Write-Host "Launching app $appId via Steam..."
Start-Process $steamExe -ArgumentList "-applaunch", $appId, "-windowed", "-enable_logging"

Write-Host "Waiting for Rome window..."
python -c @"
import time
from comstar_game_ai.game_io.window import find_game_window
from comstar_game_ai.shared.config import load_config
from comstar_game_ai.game_io.display.monitors import move_window_to_monitor

cfg = load_config()
subs = cfg.get('game', {}).get('window_title_substrings', ['Rome'])
mon = cfg.get('display', {}).get('game_monitor_index', 2)
for _ in range(120):
    w = find_game_window(subs)
    if w:
        move_window_to_monitor(w.hwnd, mon)
        print(f'Game window on monitor {mon}: {w.title}')
        break
    time.sleep(2)
else:
    raise SystemExit('Rome window not found after 240s')
"@
