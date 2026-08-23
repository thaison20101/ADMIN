# Windows hourly runner for Drive pipeline (MAY A ONLY)
# 2 TK Medinet + 2 bot: INBOX_CLS + MISSING CSV + TK1/TK2 CSV rematch
# Rule: ho+ten day du + nam/SDT/CCCD | dual-write CLS
#   FULL 2TK -> PROCESSED/U18 | FULL 1TK -> TK1/TK2
#   PARTIAL/mau khac -> ERROR | trung ten -> UNDER 18 | no TTHC -> MISSING
#
# Lan dau (chua FIRST_FULL_SCAN_DONE): full-scan 2 bot
# Sau do: hourly nhe
#
# Installed by: .\pipeline\install_hourly_task.ps1

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
Set-Location $Repo

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$env:PYTHONUNBUFFERED = "1"
try {
  [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
  $OutputEncoding = [System.Text.UTF8Encoding]::new($false)
} catch {}

# 2 TK (cung hardcode trong pipeline/medinet_creds.py)
if (-not $env:MEDINET_USER) { $env:MEDINET_USER = "pkdkthuankieu" }
if (-not $env:MEDINET_PASS) { $env:MEDINET_PASS = "P@ssw0rd" }
if (-not $env:MEDINET_USER_2) { $env:MEDINET_USER_2 = "pkdk_Thuankieu" }
if (-not $env:MEDINET_PASS_2) { $env:MEDINET_PASS_2 = "pkdk_Thuankieu#2026" }

if (-not (Test-Path ".\pipeline\config.local.json")) {
  Copy-Item ".\pipeline\config.example.json" ".\pipeline\config.local.json" -Force
}

& python ".\pipeline\ensure_config.py" | Out-Null

$MissingBudget = 2500

$buildRootFile = Join-Path $env:TEMP "pkdk_build_root.txt"
& python ".\pipeline\resolve_build_root.py" --out "$buildRootFile" | Out-Null
if (Test-Path -LiteralPath $buildRootFile) {
  $BuildRoot = (Get-Content -LiteralPath $buildRootFile -Encoding UTF8 -Raw).Trim()
} else {
  $BuildRoot = Join-Path $Repo "pipeline\work\build"
}

function Ensure-Dir([string]$Path) {
  try { New-Item -ItemType Directory -Force -Path $Path | Out-Null; return $true }
  catch { Write-Host "WARN: cannot create $Path"; return $false }
}

$LocalLogDir = Join-Path $Repo "pipeline\work\logs"
Ensure-Dir $LocalLogDir | Out-Null
$logDirOk = Ensure-Dir (Join-Path $BuildRoot "logs")
Ensure-Dir (Join-Path $BuildRoot "excel_preview") | Out-Null
Ensure-Dir (Join-Path $BuildRoot "missing_or_updated") | Out-Null
Ensure-Dir (Join-Path $BuildRoot "cases_snapshot") | Out-Null

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
if ($logDirOk) {
  $log = Join-Path $BuildRoot ("logs\hourly-" + $stamp + ".log")
  $logInbox = Join-Path $BuildRoot ("logs\hourly-inbox-" + $stamp + ".log")
  $logMiss = Join-Path $BuildRoot ("logs\hourly-missing-" + $stamp + ".log")
} else {
  $log = Join-Path $LocalLogDir ("hourly-" + $stamp + ".log")
  $logInbox = Join-Path $LocalLogDir ("hourly-inbox-" + $stamp + ".log")
  $logMiss = Join-Path $LocalLogDir ("hourly-missing-" + $stamp + ".log")
}

$FlagFull = Join-Path $BuildRoot "FIRST_FULL_SCAN_DONE.txt"
$doFull = -not (Test-Path -LiteralPath $FlagFull)

function Start-TwoBots {
  param(
    [string[]]$ExtraInbox = @(),
    [string[]]$ExtraMissing = @("--missing-budget", "$MissingBudget")
  )
  $argsInbox = @("-u", ".\pipeline\hourly_sync.py", "--bot", "inbox", "--missing-budget", "0") + $ExtraInbox
  $argsMiss = @("-u", ".\pipeline\hourly_sync.py", "--bot", "missing") + $ExtraMissing
  $b1 = Start-Process -FilePath "python" -ArgumentList $argsInbox -WorkingDirectory $Repo `
    -PassThru -NoNewWindow -RedirectStandardOutput $logInbox -RedirectStandardError ($logInbox + ".err")
  $b2 = Start-Process -FilePath "python" -ArgumentList $argsMiss -WorkingDirectory $Repo `
    -PassThru -NoNewWindow -RedirectStandardOutput $logMiss -RedirectStandardError ($logMiss + ".err")
  Write-Host ("Bot INBOX  PID={0} log={1}" -f $b1.Id, $logInbox)
  Write-Host ("Bot MISSING PID={0} log={1}" -f $b2.Id, $logMiss)
  Wait-Process -Id $b1.Id, $b2.Id -ErrorAction SilentlyContinue
  # Force refresh ExitCode (some PS versions leave null until HasExited checked)
  $null = $b1.HasExited; $null = $b2.HasExited
  $c1 = $b1.ExitCode
  $c2 = $b2.ExitCode
  if ($null -eq $c1) {
    $err1 = Get-Content ($logInbox + ".err") -Raw -ErrorAction SilentlyContinue
    $c1 = if ($err1 -match "Traceback|Error") { 1 } else { 0 }
  }
  if ($null -eq $c2) {
    $err2 = Get-Content ($logMiss + ".err") -Raw -ErrorAction SilentlyContinue
    $c2 = if ($err2 -match "Traceback|Error") { 1 } else { 0 }
  }
  Write-Host ("Bot exit: inbox={0} missing={1}" -f $c1, $c2)
  return [Math]::Max([int]$c1, [int]$c2)
}

$header = @(
  "BuildRoot: $BuildRoot"
  "Accounts: pkdkthuankieu + pkdk_Thuankieu (merged TTHC index)"
  "INBOX: G:\Drive cua toi\PKDK_Thuankieu_Pipeline\INBOX_CLS"
  "Rule: ho+ten+nam sinh | FULL->PROCESSED/U18 | PARTIAL->ERROR | no TTHC 2TK->MISSING"
  "doFull=$doFull missing_budget=$MissingBudget"
)
$header | ForEach-Object { Write-Host $_ }
$header | Set-Content -LiteralPath $log -Encoding utf8

$started = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

& python ".\pipeline\assert_g_pipeline.py"
if ($LASTEXITCODE -ne 0) {
  Write-Host "ABORT: G: chua san. Mo Google Drive Desktop."
  "started=$started`nended=$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')`nexit=2`nabort=g_drive`n" |
    Set-Content -LiteralPath (Join-Path $BuildRoot "logs\LAST_HOURLY_OK.txt") -Encoding utf8 -ErrorAction SilentlyContinue
  exit 2
}

if ($doFull) {
  Write-Host "MODE: FIRST FULL SCAN 2 BOT (INBOX + MISSING)"
  $code = Start-TwoBots -ExtraInbox @("--full-scan", "--repair") -ExtraMissing @(
    "--full-scan", "--repair", "--missing-budget", "$MissingBudget"
  )
  if ($code -eq 0) {
    try {
      Set-Content -LiteralPath $FlagFull -Value ("done=" + (Get-Date -Format "yyyy-MM-dd HH:mm:ss")) -Encoding utf8
      Write-Host "OK: FIRST_FULL_SCAN_DONE - lan sau hourly INBOX+MISSING"
    } catch {}
  }
} else {
  Write-Host "MODE: HOURLY 2 BOT - INBOX_CLS disk + MISSING CSV rematch"
  $code = Start-TwoBots
}

& python ".\pipeline\print_counts.py" | ForEach-Object { Write-Host $_ }
& python ".\pipeline\super_data_status.py" --publish | Out-Null

$ended = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$hb = @(
  "started=$started"
  "ended=$ended"
  "exit=$code"
  "log=$log"
  "log_inbox=$logInbox"
  "log_missing=$logMiss"
  "full=$doFull"
  "accounts=pkdkthuankieu+pkdk_Thuankieu"
  "missing_budget=$MissingBudget"
) -join "`n"
try {
  $hbPath = Join-Path $BuildRoot "logs\LAST_HOURLY_OK.txt"
  Ensure-Dir (Join-Path $BuildRoot "logs") | Out-Null
  Set-Content -LiteralPath $hbPath -Value $hb -Encoding utf8
} catch {}
try {
  Set-Content -LiteralPath (Join-Path $LocalLogDir "LAST_HOURLY_OK.txt") -Value $hb -Encoding utf8
} catch {}

$snapDir = Join-Path $BuildRoot "cases_snapshot"
if (Ensure-Dir $snapDir) {
  Copy-Item ".\tracking\cases.csv" (Join-Path $snapDir "cases-$stamp.csv") -Force -ErrorAction SilentlyContinue
}

Write-Host "Log main: $log"
Write-Host "Exit code: $code"
if ($code -ne 0) { exit $code }
