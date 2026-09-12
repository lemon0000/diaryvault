param(
  [int]$Port = 8765
)

$ErrorActionPreference = "Stop"

$Cloudflared = Get-Command cloudflared -ErrorAction SilentlyContinue
if (-not $Cloudflared) {
  throw "cloudflared not found. Install it first, then rerun this script."
}

$LocalApi = "http://127.0.0.1:$Port"

try {
  Invoke-WebRequest -UseBasicParsing -Uri "$LocalApi/openapi.json" -TimeoutSec 5 | Out-Null
}
catch {
  throw "DiaryVault API is not reachable at $LocalApi. Start scripts\run-diaryvault-api.ps1 first."
}

Write-Host "Starting Cloudflare Quick Tunnel for $LocalApi"
Write-Host "Keep this window open. Copy the printed https://*.trycloudflare.com URL for ChatGPT Actions."

& $Cloudflared.Source tunnel --url $LocalApi
