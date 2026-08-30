# Everything CI would run: lint, types, tests, production build.
. (Join-Path $PSScriptRoot 'common.ps1')

Write-Host '== ruff =='
Invoke-Backend -Arguments @('-m', 'ruff', 'check', '.')

Write-Host '== pytest =='
Invoke-Backend -Arguments @('-m', 'pytest')

Write-Host '== frontend =='
Push-Location $FrontendDir
try {
    npx oxlint
    if ($LASTEXITCODE -ne 0) { throw 'oxlint failed' }
    npm run build
    if ($LASTEXITCODE -ne 0) { throw 'frontend build failed' }
}
finally { Pop-Location }

Write-Host ''
Write-Host 'All checks passed.'
