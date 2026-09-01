# Push the local catalog to a deployed API. Arguments go straight to upload.py,
# whose header explains the credentials: npm run db:upload -- --dry-run
. (Join-Path $PSScriptRoot 'common.ps1')

Invoke-Backend -Arguments (@((Join-Path $PSScriptRoot 'upload.py')) + $args)
