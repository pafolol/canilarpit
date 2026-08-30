# Shared paths and the venv python. Dot-source this from the other scripts.

$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $RepoRoot 'backend'
$FrontendDir = Join-Path $RepoRoot 'frontend'
$VenvDir = Join-Path $RepoRoot '.venv'
$VenvPython = Join-Path $VenvDir 'Scripts\python.exe'

function Get-BackendPython {
    if (Test-Path $VenvPython) { return $VenvPython }
    throw "No virtual environment at $VenvDir. Run: npm run setup"
}

function Invoke-Backend {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    $python = Get-BackendPython
    Push-Location $BackendDir
    try {
        & $python @Arguments
        if ($LASTEXITCODE -ne 0) { throw "python $($Arguments -join ' ') failed with exit code $LASTEXITCODE" }
    }
    finally { Pop-Location }
}
