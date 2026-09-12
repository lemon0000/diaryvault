param(
  [string]$HostName = "127.0.0.1",
  [int]$Port = 8766,
  [string]$McpPath = "/mcp",
  [switch]$NoToken,
  [string[]]$AllowHost = @(),
  [string[]]$AllowOrigin = @()
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Vault = Join-Path $ProjectRoot "DiaryVault"
$TokenFile = Join-Path $ProjectRoot ".secrets\diaryvault-api-token.txt"
$LogDir = Join-Path $Vault "logs"

New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$LogFile = Join-Path $LogDir "mcp-http-$Stamp.log"

if (-not (Test-Path -LiteralPath $Python)) {
  throw "Python venv not found: $Python"
}
if (-not (Test-Path -LiteralPath $Vault)) {
  throw "Vault not found: $Vault"
}
if (-not $NoToken -and -not (Test-Path -LiteralPath $TokenFile)) {
  throw "API token file not found: $TokenFile; run scripts\new-diaryvault-api-token.ps1 first"
}

$ArgsList = @(
  "-m", "diaryvault", "mcp-http",
  "--vault", $Vault,
  "--host", $HostName,
  "--port", "$Port",
  "--path", $McpPath,
  "--log-level", "warning"
)

if (-not $NoToken) {
  $ArgsList += @("--api-token-file", $TokenFile)
}
foreach ($Item in $AllowHost) {
  $ArgsList += @("--allow-host", $Item)
}
foreach ($Item in $AllowOrigin) {
  $ArgsList += @("--allow-origin", $Item)
}

$StartedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Set-Content -LiteralPath $LogFile -Value "Started DiaryVault MCP HTTP at $StartedAt on ${HostName}:$Port$McpPath" -Encoding utf8

& $Python @ArgsList
exit $LASTEXITCODE
