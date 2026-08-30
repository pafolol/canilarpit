# Run the API on http://127.0.0.1:8000 with reload.
. (Join-Path $PSScriptRoot 'common.ps1')
Invoke-Backend -Arguments @('-m', 'uvicorn', 'app.main:app', '--reload', '--host', '127.0.0.1', '--port', '8000')
