Param(
    [switch]$PythonOnly,
    [switch]$RustOnly
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot ".."))
$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"

if (Test-Path $VenvPython) {
    $env:ADUIB_RPC_PYTHON = $VenvPython
    Write-Host "Using Python: $env:ADUIB_RPC_PYTHON"
} else {
    Write-Host "Warning: .venv not found; falling back to python on PATH"
}

if (-not $RustOnly) {
    Push-Location $RepoRoot
    try {
        & $env:ADUIB_RPC_PYTHON -m pytest -q
    } finally {
        Pop-Location
    }
}

if (-not $PythonOnly) {
    Push-Location (Join-Path $RepoRoot "rust-sdk")
    try {
        cargo test -q
    } finally {
        Pop-Location
    }
}
