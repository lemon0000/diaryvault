param(
  [string]$TaskName = "DiaryVault Daily Sync",
  [string]$At = "03:00"
)

$ErrorActionPreference = "Stop"

$ScriptPath = Join-Path $PSScriptRoot "run-diaryvault-daily.ps1"
if (-not (Test-Path -LiteralPath $ScriptPath)) {
  throw "Daily sync script not found: $ScriptPath"
}

$Action = New-ScheduledTaskAction `
  -Execute "powershell.exe" `
  -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`""
$Trigger = New-ScheduledTaskTrigger -Daily -At $At
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable

Register-ScheduledTask `
  -TaskName $TaskName `
  -Action $Action `
  -Trigger $Trigger `
  -Settings $Settings `
  -Description "Runs DiaryVault daily sync for Nideriji." `
  -Force

