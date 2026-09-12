param(
  [string]$TaskName = "DiaryVault Memory API"
)

$ErrorActionPreference = "Stop"

$ScriptPath = Join-Path $PSScriptRoot "run-diaryvault-api.ps1"
if (-not (Test-Path -LiteralPath $ScriptPath)) {
  throw "API script not found: $ScriptPath"
}

$Action = New-ScheduledTaskAction `
  -Execute "powershell.exe" `
  -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$ScriptPath`""
$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable

Register-ScheduledTask `
  -TaskName $TaskName `
  -Action $Action `
  -Trigger $Trigger `
  -Settings $Settings `
  -Description "Runs the local token-protected DiaryVault memory API at logon." `
  -Force
