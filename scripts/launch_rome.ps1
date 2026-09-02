# Launch Rome Remastered via Steam (required for DRM) with comstar-telemetry mod
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

$cfg = Get-Content "config\default.yaml" -Raw
$appId = 885970
if ($cfg -match "steam_app_id:\s*(\d+)") { $appId = [int]$Matches[1] }

$gameRoot = "C:\Program Files (x86)\Steam\steamapps\common\Total War ROME REMASTERED"
$modsRoot = Join-Path $env:LOCALAPPDATA "Feral Interactive\Total War ROME REMASTERED\Mods"
$enabledPath = Join-Path $modsRoot "Metadata\Enabled Mods\Rome.json"

if (-not (Test-Path (Join-Path $modsRoot "Local Mods\comstar-telemetry\modinfo.json"))) {
    Write-Host "Installing telemetry mod..."
    & "$PSScriptRoot\install_telemetry_mod.ps1"
}

$enabled = @{
    local   = @("comstar-telemetry")
    steam   = @()
    version = "2.0.5"
}
$enabled | ConvertTo-Json | Set-Content $enabledPath -Encoding UTF8
Write-Host "Enabled comstar-telemetry in Rome.json"

$steam = (Get-ItemProperty "HKCU:\Software\Valve\Steam" -ErrorAction SilentlyContinue).SteamPath
if (-not $steam) {
    Write-Error "Steam not found. Launch Rome manually from Steam with launch options: -windowed -enable_logging -verbose_script_logging"
}
$steamExe = Join-Path $steam "steam.exe"

# Launch args from merged config (default.yaml + local.yaml)
$launchArgsJson = python -c @"
import json
from comstar_game_ai.shared.config import load_config
cfg = load_config()
args = (cfg.get('game') or {}).get('launch_args') or ['-windowed', '-enable_logging', '-verbose_script_logging']
print(json.dumps(args))
"@
$gameArgs = $launchArgsJson | ConvertFrom-Json
$launchArgs = @("-applaunch", "$appId") + @($gameArgs)
Write-Host "Launching via Steam: $steamExe $($launchArgs -join ' ')"
Start-Process -FilePath $steamExe -ArgumentList $launchArgs

Write-Host "Waiting for Rome game window (launcher may appear first)..."
python -c @"
import time
import win32process
from comstar_game_ai.game_io.window import find_game_window, process_elevation_matches
from comstar_game_ai.shared.config import load_config
from comstar_game_ai.game_io.display.monitors import move_window_to_monitor

cfg = load_config()
subs = cfg.get('game', {}).get('window_title_substrings', ['Rome'])
mon = cfg.get('display', {}).get('game_monitor_index', 1)
resize = cfg.get('display', {}).get('resize_to_monitor', True)

def is_game_window(title: str) -> bool:
    t = title.lower()
    if 'total war' not in t and 'rome remastered' not in t:
        return False
    for skip in ('launcher', 'options', 'feral'):
        if skip in t:
            return False
    return True

for i in range(120):
    w = find_game_window(subs)
    if w and is_game_window(w.title):
        _, pid = win32process.GetWindowThreadProcessId(w.hwnd)
        if not process_elevation_matches(pid):
            print('WARN: Rome and this terminal have different admin elevation.')
            print('      Monitor move may fail — launch Cursor/terminal at the same level as Steam.')
        if move_window_to_monitor(w.hwnd, mon, resize=resize, retries=20, delay_s=1.5):
            mode = 'resized' if resize else 'positioned (windowed)'
            print(f'Game window {mode} on monitor {mon}: {w.title}')
        else:
            print(f'Game window found (monitor move skipped - drag window manually): {w.title}')
        break
    time.sleep(2)
else:
    print('Timed out waiting for game window.')
    print('If the Feral launcher opened: click Play, then re-run phase 1 observation.')
    raise SystemExit(1)
"@

if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Load your Julii campaign save, then end one turn for telemetry."
Write-Host "Re-run: python scripts/run_phase1_observation.py"
