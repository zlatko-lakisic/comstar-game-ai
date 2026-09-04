# Stop Rome minimizing when you click another app (windowed/borderless).
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$prefPath = Join-Path $env:LOCALAPPDATA "Feral Interactive\Total War ROME REMASTERED\Preferences Data"
if (-not (Test-Path $prefPath)) {
    Write-Warning "Rome preferences not found: $prefPath"
    Write-Host "In Feral launcher: Advanced -> tick 'Disable App minimising on alt+tab'"
    exit 0
}

$text = [System.IO.File]::ReadAllText($prefPath)
$pattern = '(<value name="DisableMinimiseOnDeactivation" type="integer">)0(</value>)'
if ($text -match 'DisableMinimiseOnDeactivation" type="integer">1</value>') {
    Write-Host "DisableMinimiseOnDeactivation already enabled"
    exit 0
}

if ($text -notmatch $pattern) {
    Write-Warning "Could not find DisableMinimiseOnDeactivation in preferences"
    Write-Host "In Feral launcher: Advanced -> tick 'Disable App minimising on alt+tab'"
    exit 1
}

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$newText = [regex]::Replace($text, $pattern, '${1}1${2}', 1)
[System.IO.File]::WriteAllText($prefPath, $newText, $utf8NoBom)
Write-Host "Enabled DisableMinimiseOnDeactivation (Rome stays visible when focus leaves)"
