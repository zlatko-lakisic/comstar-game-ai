# Run live ada integration tests (requires mTLS material in .cursor/secrets/)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

pytest tests/integration -v --run-integration-ada @args
