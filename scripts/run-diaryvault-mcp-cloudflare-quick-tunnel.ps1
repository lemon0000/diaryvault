param(
  [int]$Port = 8766
)

$ErrorActionPreference = "Stop"

$CloudflaredCommand = Get-Command cloudflared -ErrorAction SilentlyContinue
if ($CloudflaredCommand) {
  $CloudflaredPath = $CloudflaredCommand.Source
}
else {
  $KnownPaths = @(
    "C:\Program Files\cloudflared\cloudflared.exe",
    "C:\Program Files (x86)\cloudflared\cloudflared.exe",
    "C:\Program Files\Cloudflare\cloudflared.exe",
    "C:\Program Files (x86)\Cloudflare\cloudflared.exe"
  )
  $CloudflaredPath = $KnownPaths | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}

if (-not $CloudflaredPath) {
  throw "cloudflared not found. Install it first, then rerun this script."
}

$Client = [System.Net.Sockets.TcpClient]::new()
try {
  $Connect = $Client.BeginConnect("127.0.0.1", $Port, $null, $null)
  if (-not $Connect.AsyncWaitHandle.WaitOne(1000)) {
    throw "DiaryVault MCP HTTP is not reachable at 127.0.0.1:$Port. Start scripts\run-diaryvault-mcp-http.ps1 first."
  }
  $Client.EndConnect($Connect)
}
finally {
  $Client.Close()
}

$LocalOrigin = "http://127.0.0.1:$Port"
$HostHeader = "127.0.0.1:$Port"

Write-Host "Starting Cloudflare Quick Tunnel for $LocalOrigin"
Write-Host "Keep this window open. Use the printed https://*.trycloudflare.com/mcp URL in ChatGPT."

& $CloudflaredPath tunnel --url $LocalOrigin --http-host-header $HostHeader
