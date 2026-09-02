# Disable comstar-telemetry mod (use if campaign won't start)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$enabledPath = Join-Path $env:LOCALAPPDATA "Feral Interactive\Total War ROME REMASTERED\Mods\Metadata\Enabled Mods\Rome.json"
@{
    local   = @()
    steam   = @()
    version = "2.0.5"
} | ConvertTo-Json | Set-Content $enabledPath -Encoding UTF8

Write-Host "Disabled all local mods in Rome.json. Restart Rome from Steam."
