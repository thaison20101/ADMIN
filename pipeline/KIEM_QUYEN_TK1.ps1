# ============================================================
# KIEM QUYEN TK1: AUTH + ExecuteStore + PostData + FormViewer
# ASCII-only.
#
#   powershell -ExecutionPolicy Bypass -File .\pipeline\KIEM_QUYEN_TK1.ps1
# ============================================================

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
if (-not $Repo) { $Repo = "C:\Users\thais\ADMIN" }
Set-Location $Repo

$env:MEDINET_SSL_VERIFY = "0"
$env:MEDINET_USER = "pkdkthuankieu"
$env:MEDINET_PASS = "Qlskcd@2026"
Remove-Item Env:MEDINET_ENABLE_TK2 -ErrorAction SilentlyContinue
Remove-Item Env:MEDINET_USER_2 -ErrorAction SilentlyContinue
Remove-Item Env:MEDINET_PASS_2 -ErrorAction SilentlyContinue
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

. (Join-Path $PSScriptRoot "Resolve-PkdkPython.ps1")
$Python = Resolve-PkdkPython

Write-Host "############################################################"
Write-Host "#  KIEM QUYEN TK1 (AUTH + ExecuteStore + PostData + FV)    #"
Write-Host "############################################################"
Write-Host "ExecuteStore 403: van rematch bang PostData neu PostData OK."
Write-Host "Chi chuyen TK1/PROCESSED khi CLS da dien du + verify."
Write-Host ""

& $Python ".\pipeline\ensure_config.py"
& $Python ".\pipeline\medinet_creds.py" --write --user pkdkthuankieu --pass Qlskcd@2026
& $Python ".\pipeline\probe_both_accounts.py"
$code = $LASTEXITCODE

Write-Host ""
if ($code -eq 0) {
  Write-Host "OK: co the dien CLS. Chay QUET_GAP_VA_BAT_HOURLY.ps1"
} else {
  Write-Host "DUNG: thieu quyen dien CLS. Bao Medinet/IT."
  Write-Host "Bo qua TK2 theo yeu cau."
}
exit $code
