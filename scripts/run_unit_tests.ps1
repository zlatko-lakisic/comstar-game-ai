# Run unit tests (offline)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

pytest tests/unit -v @args
