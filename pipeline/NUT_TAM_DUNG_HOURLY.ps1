# Desktop button: TAM DUNG lich hourly.
# KHONG xoa / KHONG doi rule quet-dien. Bat lai = cung rule nhu cu.
# ASCII-only.
#
#   powershell -ExecutionPolicy Bypass -File .\pipeline\NUT_TAM_DUNG_HOURLY.ps1

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
Set-Location $Repo

Write-Host "============================================================"
Write-Host " PKDK - TAM DUNG HOURLY"
Write-Host " Chi TAT lich chay. Rule quet/dien VAN GIU (auto_cycle)."
Write-Host " Bat lai sau: nut 'PKDK - Bat lai khi co INBOX' = cung rule."
Write-Host "============================================================"

& powershell -NoProfile -ExecutionPolicy Bypass -File ".\pipeline\TAM_NGUNG_HOURLY.ps1"
$code = $LASTEXITCODE

Get-Process -Name python*, py* -ErrorAction SilentlyContinue | ForEach-Object {
  Write-Host ("  stop leftover PID=" + $_.Id)
  Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
}

$markDir = Join-Path $Repo "pipeline\work\build\logs"
if (-not (Test-Path -LiteralPath $markDir)) {
  New-Item -ItemType Directory -Force -Path $markDir | Out-Null
}
$sha = ""
try { $sha = (git rev-parse --short HEAD) } catch {}
$mark = @(
  "state=HOURLY_PAUSED"
  ("at=" + (Get-Date -Format "yyyy-MM-dd HH:mm:ss"))
  ("head=" + $sha)
  "rules=UNCHANGED (auto_cycle still on disk)"
  "resume=Desktop 'PKDK - Bat lai khi co INBOX' -> cung rule quet"
) -join "`n"
Set-Content -LiteralPath (Join-Path $markDir "HOURLY_PAUSE_STATE.txt") -Value $mark -Encoding utf8

Write-Host ""
if ($code -eq 0) {
  Write-Host "OK: Hourly DA TAM DUNG. Rule quet KHONG bi xoa."
} else {
  Write-Host "WARN: Tam dung co loi (thu Run as Administrator)."
}
Write-Host "Khi co them PDF INBOX_CLS: double-click 'PKDK - Bat lai khi co INBOX'."
Write-Host "============================================================"
exit $code
