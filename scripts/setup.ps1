# One-time setup: virtual environment, Python dependencies, node modules, .env files.
. (Join-Path $PSScriptRoot 'common.ps1')

if (-not (Test-Path $VenvPython)) {
    Write-Host 'Creating the virtual environment...'
    python -m venv $VenvDir
}

Write-Host 'Installing the backend...'
& $VenvPython -m pip install --upgrade pip --quiet
& $VenvPython -m pip install -e "$BackendDir[dev]"
if ($LASTEXITCODE -ne 0) { throw 'Backend install failed' }

Write-Host 'Installing the frontend...'
Push-Location $FrontendDir
try {
    npm install
    if ($LASTEXITCODE -ne 0) { throw 'npm install failed' }
}
finally { Pop-Location }

foreach ($pair in @(@($BackendDir, 'backend'), @($FrontendDir, 'frontend'))) {
    $envPath = Join-Path $pair[0] '.env'
    $examplePath = Join-Path $pair[0] '.env.example'
    if (-not (Test-Path $envPath) -and (Test-Path $examplePath)) {
        Copy-Item $examplePath $envPath
        Write-Host "Created $($pair[1])/.env from the example."
    }
}

Write-Host ''
Write-Host 'Next:'
Write-Host '  1. Set DATABASE_URL in backend/.env and create that database.'
Write-Host '  2. npm run db:migrate'
Write-Host '  3. npm run db:seed'
Write-Host '  4. npm run dev'
