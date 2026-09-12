param(
  [string]$Vault = "",
  [int]$Port = 8767,
  [string]$Path = "/mcp"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
if (-not $Vault) {
  $Vault = Join-Path $ProjectRoot "DiaryVault"
}
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
  throw "Python venv not found at $Python"
}

if (-not (Test-Path -LiteralPath $Vault)) {
  throw "DiaryVault data directory not found at $Vault"
}

Write-Host "Starting DiaryVault MCP HTTP for OpenAI Secure MCP Tunnel"
Write-Host "Endpoint: http://127.0.0.1:$Port$Path"
Write-Host "This listener is local-only and has no static token. Do not expose this port through generic public tunnels."

& $Python -m diaryvault mcp-http `
  --vault $Vault `
  --host 127.0.0.1 `
  --port $Port `
  --path $Path `
  --log-level warning
