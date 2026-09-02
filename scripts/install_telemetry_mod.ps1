# Install comstar-telemetry local mod for Phase 1 script logging
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

function Write-Utf8NoBom([string]$Path, [string]$Content) {
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Content, $utf8NoBom)
}

$gameData = "C:\Program Files (x86)\Steam\steamapps\common\Total War ROME REMASTERED\Contents\Resources\Data"
$vanillaStrat = Join-Path $gameData "data\world\maps\campaign\imperial_campaign\descr_strat.txt"
$vanillaTutorial = Join-Path $gameData "data\world\maps\campaign\imperial_campaign\tutorial.txt"
$modsRoot = Join-Path $env:LOCALAPPDATA "Feral Interactive\Total War ROME REMASTERED\Mods"
$modRoot = Join-Path $modsRoot "Local Mods\comstar-telemetry"
$stratRel = "data\world\maps\campaign\imperial_campaign"
$stratDir = Join-Path $modRoot $stratRel
$stratDest = Join-Path $stratDir "descr_strat.txt"
$tutorialDest = Join-Path $stratDir "tutorial.txt"
$snippetPath = Resolve-Path "mod\comstar_telemetry_snippet.txt"
$snippetMarker = ";; comstar Game AI telemetry"

if (-not (Test-Path $vanillaStrat)) {
    Write-Error "Vanilla descr_strat not found: $vanillaStrat"
}
if (-not (Test-Path $vanillaTutorial)) {
    Write-Error "Vanilla tutorial.txt not found: $vanillaTutorial"
}

New-Item -ItemType Directory -Path $stratDir -Force | Out-Null

# Imperial campaign loads one script only: tutorial.txt (listed in descr_strat).
$strat = [System.IO.File]::ReadAllText($vanillaStrat)
$strat = [regex]::Replace($strat, "\r?\ncomstar_telemetry\.txt\r?\n", "`r`n")
Write-Utf8NoBom $stratDest ($strat.TrimEnd() + "`r`n")
Write-Host "Installed descr_strat.txt (tutorial.txt only, no BOM)"

$snippet = ([System.IO.File]::ReadAllText($snippetPath)).TrimEnd()
$tutorial = [System.IO.File]::ReadAllText($vanillaTutorial)
if ($tutorial -notmatch [regex]::Escape($snippetMarker)) {
    if ($tutorial -notmatch 'end_script;') {
        Write-Error "tutorial.txt missing end_script marker - cannot inject telemetry"
    }
    $replacement = "$snippetMarker`r`n$snippet`r`n" + 'end_script;'
    $tutorial = $tutorial.Replace('end_script;', $replacement)
    Write-Host "Injected telemetry into tutorial.txt"
} else {
    Write-Host "tutorial.txt already contains comstar telemetry snippet"
}
Write-Utf8NoBom $tutorialDest $tutorial

$modinfo = @{
    Description = "Comstar Game AI Phase 1 telemetry (NewTurnStart script_log in tutorial.txt)"
    "Mod Name"  = "comstar-telemetry"
    "Supports Alex" = $false
    "Supports BI"   = $false
    "Supports Rome" = $true
    Tags          = @("comstar", "telemetry")
    Visibility    = 1
}
Write-Utf8NoBom (Join-Path $modRoot "modinfo.json") ($modinfo | ConvertTo-Json)

$filelist = @(
    @{ filename = "data/world/maps/campaign/imperial_campaign/descr_strat.txt"; checksum = "Blacklisted" }
    @{ filename = "data/world/maps/campaign/imperial_campaign/tutorial.txt"; checksum = "Blacklisted" }
)
Write-Utf8NoBom (Join-Path $modRoot "filelist.json") ($filelist | ConvertTo-Json)

Write-Host "Installed mod at: $modRoot"
Write-Host "In Feral launcher: tick comstar-telemetry, Regenerate Manifest, then Play."
Write-Host "Reload your campaign save (scripts load on campaign start/load) and end one turn."
