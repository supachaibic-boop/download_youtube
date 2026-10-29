$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Test-Path .env)) {
  $bytes = New-Object byte[] 32
  $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
  $rng.GetBytes($bytes)
  $rng.Dispose()
  $token = -join ($bytes | ForEach-Object { $_.ToString('x2') })
  Set-Content -Path .env -Value "API_TOKEN=$token`nALLOWED_ORIGINS=" -Encoding ascii
}
docker compose up -d --build
if ($LASTEXITCODE -ne 0) { throw 'Docker failed. Start Docker Desktop and retry.' }
Write-Host "Open http://localhost:8080 and paste this API token:"
Get-Content .env | Where-Object { $_ -like 'API_TOKEN=*' }
Start-Process 'http://localhost:8080'
