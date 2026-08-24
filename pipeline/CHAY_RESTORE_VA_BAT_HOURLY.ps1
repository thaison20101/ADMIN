# ============================================================
# 1 LENH: pull + restore PROCESSED bi day nham + BAT LAI hourly
#
# Copy-paste khi ngoi may A:
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_RESTORE_VA_BAT_HOURLY.ps1
# ============================================================

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
if (-not $Repo) { $Repo = "C:\Users\thais\ADMIN" }
Set-Location $Repo

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

Write-Host ""
Write-Host "==== 1/3 git pull ===="
if (Test-Path -LiteralPath (Join-Path $Repo ".git")) {
  git fetch origin
  git checkout cursor/drive-hourly-pipeline-df0f
  git pull origin cursor/drive-hourly-pipeline-df0f
} else {
  Write-Host "Khong co .git - bo qua pull."
}

Write-Host "==== 2/3 restore PROCESSED tu MISSING ===="
& python ".\pipeline\ensure_config.py"
Write-Host "-- dry-run (chi liet ke) --"
& python ".\pipeline\restore_processed_from_missing.py" --dry-run
Write-Host "-- restore that --"
& python ".\pipeline\restore_processed_from_missing.py"

Write-Host "==== 3/3 BAT LAI hourly (khong dung BAT_LAI_HOURLY.ps1 neu file cu bi loi) ===="
$TaskName = "PKDK_Hourly_Sync"
try {
  Enable-ScheduledTask -TaskName $TaskName -ErrorAction Stop | Out-Null
  Write-Host "OK: Enable-ScheduledTask"
} catch {
  schtasks.exe /Change /TN $TaskName /ENABLE | Out-Null
  Write-Host "OK: schtasks ENABLE (fallback)"
}
Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue | Format-List TaskName, State

Write-Host ""
Write-Host "XONG. Hourly State=Ready la OK. Chi quet INBOX + MISSING, ky 01/07 -> hom nay."
exit 0
