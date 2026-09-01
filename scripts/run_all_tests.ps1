# Run full local test suite (unit + ada integration + acceptance)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

Write-Host "=== Unit tests ==="
pytest tests/unit -v --tb=short
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "=== ada integration tests ==="
pytest tests/integration -v --run-integration-ada --tb=short
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "=== Acceptance tests ==="
pytest tests/acceptance -v --tb=short
exit $LASTEXITCODE
