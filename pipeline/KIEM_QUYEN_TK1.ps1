# ============================================================
# KIEM QUYEN TK1 tren Medinet API (bo qua TK2)
# Login OK van co the bi 403 DRViewer -> khong lay TTHC / khong dien CLS.
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
Write-Host "#  KIEM QUYEN TK1 (login + DRViewer)                        #"
Write-Host "############################################################"
Write-Host "Web mo duoc quanlyskcd KHONG dong nghia API co quyen lay TTHC."
Write-Host ""

& $Python ".\pipeline\ensure_config.py"
& $Python ".\pipeline\medinet_creds.py" --write --user pkdkthuankieu --pass Qlskcd@2026
& $Python ".\pipeline\probe_both_accounts.py"
$code = $LASTEXITCODE

Write-Host ""
if ($code -eq 0) {
  Write-Host "OK: TK1 co quyen DRViewer - co the QUET_GAP_VA_BAT_HOURLY.ps1"
} else {
  Write-Host "DUNG: TK1 login OK nhung DRViewer Access denied (403)."
  Write-Host "Can Medinet/IT cap lai quyen DynamicReport/DRViewer cho user pkdkthuankieu."
  Write-Host "Kiem tren Chrome: F12 > Network > mo danh sach BN > tim"
  Write-Host "  ExecuteStoreWithParam_ByDatasource  -> neu Status 403 thi dung nhu bot."
  Write-Host "Bo qua TK2 theo yeu cau (khong dung TK2)."
}
exit $code
