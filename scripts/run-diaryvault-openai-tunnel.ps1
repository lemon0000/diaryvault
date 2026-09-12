param(
  [string]$Profile = "diaryvault",
  [string]$ProfileDir = "",
  [string]$TunnelClientPath = "",
  [string]$ControlPlaneApiKeyFile = "",
  [switch]$SkipDoctor
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
if (-not $ProfileDir) {
  $ProfileDir = Join-Path $ProjectRoot ".secrets\tunnel-client-profiles"
}
if (-not $TunnelClientPath) {
  $TunnelClientPath = Join-Path $ProjectRoot ".tools\tunnel-client\tunnel-client.exe"
}
if (-not $ControlPlaneApiKeyFile) {
  $ControlPlaneApiKeyFile = Join-Path $ProjectRoot ".secrets\openai-control-plane-api-key.txt"
}

if (-not (Test-Path -LiteralPath $TunnelClientPath)) {
  throw "OpenAI tunnel-client not found at $TunnelClientPath"
}

if (-not (Test-Path -LiteralPath $ProfileDir)) {
  throw "Tunnel profile directory not found at $ProfileDir. Run scripts\init-diaryvault-openai-tunnel.ps1 first."
}

$ApiKeyRef = "env:CONTROL_PLANE_API_KEY"
if (-not $env:CONTROL_PLANE_API_KEY) {
  if (Test-Path -LiteralPath $ControlPlaneApiKeyFile) {
    $RuntimeKey = [string](Get-Content -LiteralPath $ControlPlaneApiKeyFile -Raw)
    $RuntimeKey = $RuntimeKey.Trim()
    if (-not $RuntimeKey) {
      throw "Control-plane API key file is empty: $ControlPlaneApiKeyFile"
    }
    $env:CONTROL_PLANE_API_KEY = $RuntimeKey
  }
  else {
    throw "Missing CONTROL_PLANE_API_KEY. Set the environment variable or save it to $ControlPlaneApiKeyFile"
  }
}

if (-not $SkipDoctor) {
  Write-Host "Running tunnel-client doctor for profile '$Profile'"
  & $TunnelClientPath doctor `
    --profile $Profile `
    --profile-dir $ProfileDir `
    --control-plane.api-key $ApiKeyRef `
    --explain

  if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
  }
}

Write-Host "Starting OpenAI Secure MCP Tunnel profile '$Profile'"
Write-Host "Keep this process running while ChatGPT uses DiaryVault."

& $TunnelClientPath run `
  --profile $Profile `
  --profile-dir $ProfileDir `
  --control-plane.api-key $ApiKeyRef
