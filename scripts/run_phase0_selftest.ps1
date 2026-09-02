# Phase 0 self-test runner
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

Write-Host "Comstar Game AI — Phase 0 self-tests"
Write-Host "Ensure Rome Remastered is borderless windowed if testing with game."
Write-Host ""

python -m comstar_game_ai.game_io.main --self-test-only @args
exit $LASTEXITCODE
