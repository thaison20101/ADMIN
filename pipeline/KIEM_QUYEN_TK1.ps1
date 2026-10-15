# ============================================================
# KIEM QUYEN TK1 tren Medinet API (bo qua TK2)
# Bao 3 dong: AUTH / DRViewer / FormViewer CLS.
# DRViewer 403 van OK neu FormViewer dien CLS duoc (can phieukhamId).
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
Write-Host "#  KIEM QUYEN TK1 (AUTH + DRViewer + FormViewer)            #"
Write-Host "############################################################"
Write-Host "Web mo duoc quanlyskcd KHONG dong nghia API co quyen index TTHC."
Write-Host "DRViewer 403: van dien CLS qua FormViewer neu da co phieukhamId."
Write-Host ""

& $Python ".\pipeline\ensure_config.py"
& $Python ".\pipeline\medinet_creds.py" --write --user pkdkthuankieu --pass Qlskcd@2026
& $Python ".\pipeline\probe_both_accounts.py"
$code = $LASTEXITCODE

Write-Host ""
if ($code -eq 0) {
  Write-Host "OK: co the dien CLS (DRViewer Set va/hoac FormViewer)."
  Write-Host "Neu DRViewer DENIED: rematch ten MISSING/index bi khoa; dien hang da co pid."
  Write-Host "Chay: QUET_GAP_VA_BAT_HOURLY.ps1"
} else {
  Write-Host "DUNG: TK1 login OK nhung DRViewer va FormViewer deu bi chan."
  Write-Host "Can Medinet/IT cap quyen DynamicReport/DRViewer hoac FormViewer cho pkdkthuankieu."
  Write-Host "Bo qua TK2 theo yeu cau (khong dung TK2)."
}
exit $code
