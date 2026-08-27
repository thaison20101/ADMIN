# ============================================================
# DIEN LAI CLS - CHI folder "PDF" - khong move
# ASCII-only for Windows PowerShell 5.1
#
# G:\Drive cua toi\PKDK_Thuankieu_Pipeline\PDF
#
# KHONG: tat hourly, xoa lock, ngat lenh dang chay, move PDF
# CHI: dien CLS tu PDF trong folder PDF (rule parse/Set moi)
#
# LENH 1 DONG:
#
#   cd C:\Users\thais\ADMIN; git pull origin cursor/don-g-remediation-df0f; powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_DIEN_LAI_PDF.ps1 -Apply
#
# Dry-run:
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_DIEN_LAI_PDF.ps1
#
# Tiep sau crash:
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_DIEN_LAI_PDF.ps1 -Apply -Continue
# ============================================================

param(
  [switch]$Apply,
  [switch]$Continue,
  [switch]$SkipPull,
  [int]$Limit = 0
)

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
if (-not $Repo) { $Repo = "C:\Users\thais\ADMIN" }
Set-Location $Repo

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$env:PYTHONUNBUFFERED = "1"
$env:MEDINET_USER = "pkdkthuankieu"
$env:MEDINET_PASS = "P@ssw0rd"
$env:MEDINET_USER_2 = "pkdk_Thuankieu"
$env:MEDINET_PASS_2 = "pkdk_Thuankieu#2026"

$Branch = "cursor/don-g-remediation-df0f"
$FolderName = "PDF"

Write-Host "############################################################"
Write-Host "#  DIEN LAI CLS - CHI folder PDF - KHONG MOVE             #"
Write-Host "#  KHONG tat hourly / KHONG xoa lock / KHONG ngat lenh    #"
Write-Host "############################################################"

if (-not $SkipPull) {
  Write-Host "==== git pull $Branch ===="
  & git pull origin $Branch
}

& python ".\pipeline\assert_g_pipeline.py"
if ($LASTEXITCODE -ne 0) {
  Write-Host "DUNG: G: chua san."
  exit 2
}

# Lock rieng: khong tranh / xoa lock refill ToanBo hay hourly
$argsPy = @(
  "-u", ".\pipeline\refill_cls_inplace.py",
  "--folder", $FolderName,
  "--lock-name", "refill_cls_pdf"
)
if ($Apply) { $argsPy += "--apply" }
if ($Continue) { $argsPy += "--resume" }
if ($Limit -gt 0) { $argsPy += @("--limit", "$Limit") }

Write-Host ""
Write-Host "==== Quet CHI folder PDF - dien CLS, khong move ===="
Write-Host "KHONG goi TAM_NGUNG_HOURLY / KHONG clear locks"
if ($Continue) {
  Write-Host "CONTINUE: skip PDF da checkpoint"
}
if (-not $Apply) {
  Write-Host "MODE: DRY-RUN - them -Apply de ghi Medinet"
} else {
  Write-Host "MODE: APPLY"
}

Write-Host ("CMD: python " + ($argsPy -join " "))
& python @argsPy
$code = $LASTEXITCODE
if ($null -eq $code) { $code = -1 }

Write-Host ""
Write-Host "Log: pipeline\work\build\logs\REFILL_*.txt"
if ($code -ne 0) {
  Write-Host "!!!! Exit=$code - CHUA XONG. Them -Continue neu crash giua chung."
}

Write-Host ("Exit=$code")
exit $code
