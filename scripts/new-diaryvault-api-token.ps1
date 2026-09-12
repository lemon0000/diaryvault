param(
  [string]$TokenPath,
  [switch]$Rotate
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
if (-not $TokenPath) {
  $TokenPath = Join-Path $ProjectRoot ".secrets\diaryvault-api-token.txt"
}

$TokenDir = Split-Path -Parent $TokenPath
New-Item -ItemType Directory -Path $TokenDir -Force | Out-Null

if ((Test-Path -LiteralPath $TokenPath) -and -not $Rotate) {
  $Existing = (Get-Content -Raw -LiteralPath $TokenPath).Trim()
  Write-Host "API token already exists: $TokenPath"
  Write-Host "Length: $($Existing.Length) characters"
  Write-Host "Use -Rotate to replace it."
  exit 0
}

$Bytes = New-Object byte[] 32
$Rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
try {
  $Rng.GetBytes($Bytes)
}
finally {
  $Rng.Dispose()
}
$Token = [Convert]::ToBase64String($Bytes).TrimEnd("=").Replace("+", "-").Replace("/", "_")

Set-Content -LiteralPath $TokenPath -Value $Token -Encoding ascii -NoNewline

Write-Host "Wrote API token: $TokenPath"
Write-Host "Length: $($Token.Length) characters"
