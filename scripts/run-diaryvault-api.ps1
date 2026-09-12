param(
  [string]$HostName = "127.0.0.1",
  [int]$Port = 8765
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Vault = Join-Path $ProjectRoot "DiaryVault"
$TokenFile = Join-Path $ProjectRoot ".secrets\diaryvault-api-token.txt"
$LogDir = Join-Path $Vault "logs"

New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$LogFile = Join-Path $LogDir "api-$Stamp.log"

if (-not (Test-Path -LiteralPath $Python)) {
  throw "Python venv not found: $Python"
}
if (-not (Test-Path -LiteralPath $Vault)) {
  throw "Vault not found: $Vault"
}
if (-not (Test-Path -LiteralPath $TokenFile)) {
  throw "API token file not found: $TokenFile; run scripts\new-diaryvault-api-token.ps1 first"
}

function Test-LocalPort {
  param(
    [string]$TargetHost,
    [int]$TargetPort
  )

  $Client = [System.Net.Sockets.TcpClient]::new()
  try {
    $Connect = $Client.BeginConnect($TargetHost, $TargetPort, $null, $null)
    if (-not $Connect.AsyncWaitHandle.WaitOne(300)) {
      return $false
    }
    $Client.EndConnect($Connect)
    return $true
  }
  catch {
    return $false
  }
  finally {
    $Client.Close()
  }
}

$CheckHost = $HostName
if ($HostName -eq "0.0.0.0" -or $HostName -eq "::") {
  $CheckHost = "127.0.0.1"
}

if (Test-LocalPort -TargetHost $CheckHost -TargetPort $Port) {
  "DiaryVault API already listening on ${CheckHost}:$Port" | Tee-Object -FilePath $LogFile
  exit 0
}

& $Python -m diaryvault serve `
  --vault $Vault `
  --host $HostName `
  --port $Port `
  --api-token-file $TokenFile *>&1 |
  Tee-Object -FilePath $LogFile

exit $LASTEXITCODE
