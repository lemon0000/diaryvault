$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Vault = Join-Path $ProjectRoot "DiaryVault"
$Secrets = Join-Path $ProjectRoot ".secrets\nideriji.env"
$LogDir = Join-Path $Vault "logs"

New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$LogFile = Join-Path $LogDir "daily-$Stamp.log"

if (-not (Test-Path -LiteralPath $Python)) {
  throw "Python venv not found: $Python"
}
if (-not (Test-Path -LiteralPath $Secrets)) {
  throw "Secrets file not found: $Secrets"
}

& $Python -m diaryvault daily --vault $Vault --mode mine --days 14 --secrets-file $Secrets *>&1 |
  Tee-Object -FilePath $LogFile
$SyncExit = $LASTEXITCODE

if ($SyncExit -ne 0) {
  exit $SyncExit
}

& $Python -m diaryvault index --vault $Vault *>&1 |
  Tee-Object -FilePath $LogFile -Append
$IndexExit = $LASTEXITCODE

if ($IndexExit -ne 0) {
  exit $IndexExit
}

& $Python -m diaryvault semantic-index --vault $Vault --skip-if-unavailable *>&1 |
  Tee-Object -FilePath $LogFile -Append
$SemanticExit = $LASTEXITCODE

if ($SemanticExit -ne 0) {
  exit $SemanticExit
}

& $Python -m diaryvault stats --vault $Vault --write-report *>&1 |
  Tee-Object -FilePath $LogFile -Append
$StatsExit = $LASTEXITCODE

if ($StatsExit -ne 0) {
  exit $StatsExit
}

& $Python -m diaryvault validate --vault $Vault *>&1 |
  Tee-Object -FilePath $LogFile -Append
$ValidateExit = $LASTEXITCODE

exit $ValidateExit
