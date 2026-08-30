# Publish backend/content/guides/*.json and the default categories.
. (Join-Path $PSScriptRoot 'common.ps1')
Invoke-Backend -Arguments @('-m', 'app.cli', 'seed')
