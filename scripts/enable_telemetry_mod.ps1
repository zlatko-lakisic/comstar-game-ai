# Enable comstar-telemetry mod before launching Rome from the Feral launcher.
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$modsRoot = Join-Path $env:LOCALAPPDATA "Feral Interactive\Total War ROME REMASTERED\Mods"
$enabledPath = Join-Path $modsRoot "Metadata\Enabled Mods\Rome.json"

if (-not (Test-Path (Join-Path $modsRoot "Local Mods\comstar-telemetry\modinfo.json"))) {
    Write-Error "Mod not installed. Run: scripts/install_telemetry_mod.ps1"
}

@{
    local   = @("comstar-telemetry")
    steam   = @()
    version = "2.0.5"
} | ConvertTo-Json | Set-Content $enabledPath -Encoding UTF8

Write-Host "Wrote comstar-telemetry to Rome.json"
Write-Host ""
Write-Host "IMPORTANT: Launch Rome from Steam, then in the Feral launcher:"
Write-Host "  1. Open the Mods tab"
Write-Host "  2. Tick 'comstar-telemetry'"
Write-Host "  3. Click 'Regenerate Manifest' if shown"
Write-Host "  4. Click Play"
Write-Host ""
Write-Host "The launcher may clear Rome.json if you skip step 2."
