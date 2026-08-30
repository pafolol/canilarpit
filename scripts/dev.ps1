# Run the API and the dev server together. Ctrl+C stops both.
. (Join-Path $PSScriptRoot 'common.ps1')

$python = Get-BackendPython
Write-Host 'API      http://127.0.0.1:8000  (docs at /docs)'
Write-Host 'Frontend http://localhost:5173'
Write-Host ''

$api = Start-Process -FilePath $python `
    -ArgumentList '-m', 'uvicorn', 'app.main:app', '--reload', '--host', '127.0.0.1', '--port', '8000' `
    -WorkingDirectory $BackendDir -PassThru -NoNewWindow

try {
    Push-Location $FrontendDir
    try { npm run dev } finally { Pop-Location }
}
finally {
    if ($api -and -not $api.HasExited) {
        Write-Host 'Stopping the API...'
        Stop-Process -Id $api.Id -Force -ErrorAction SilentlyContinue
    }
}
