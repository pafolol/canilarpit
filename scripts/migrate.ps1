# Apply every migration to the database named by DATABASE_URL.
. (Join-Path $PSScriptRoot 'common.ps1')
Invoke-Backend -Arguments @('-m', 'alembic', 'upgrade', 'head')
