param(
  [Parameter(Mandatory = $true)]
  [string]$TunnelId,

  [string]$Profile = "diaryvault",
  [string]$ProfileDir = "",
  [string]$TunnelClientPath = "",
  [int]$Port = 8767,
  [string]$McpPath = "/mcp",
  [string]$HealthListenAddr = "127.0.0.1:8788",
  [switch]$Force
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
if (-not $ProfileDir) {
  $ProfileDir = Join-Path $ProjectRoot ".secrets\tunnel-client-profiles"
}
if (-not $TunnelClientPath) {
  $TunnelClientPath = Join-Path $ProjectRoot ".tools\tunnel-client\tunnel-client.exe"
}

if (-not (Test-Path -LiteralPath $TunnelClientPath)) {
  throw "OpenAI tunnel-client not found at $TunnelClientPath"
}

New-Item -ItemType Directory -Force -Path $ProfileDir | Out-Null

$McpServerUrl = "http://127.0.0.1:$Port$McpPath"
$InitArgs = @(
  "init",
  "--sample", "sample_mcp_remote_no_auth",
  "--profile", $Profile,
  "--profile-dir", $ProfileDir,
  "--tunnel-id", $TunnelId,
  "--mcp-server-url", $McpServerUrl,
  "--health-listen-addr", $HealthListenAddr
)

if ($Force) {
  $InitArgs += "--force"
}

Write-Host "Initializing OpenAI Secure MCP Tunnel profile '$Profile'"
Write-Host "MCP target: $McpServerUrl"
Write-Host "Profile dir: $ProfileDir"

& $TunnelClientPath @InitArgs
