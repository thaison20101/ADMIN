# ============================================================
# CAP NHAT CODE TU GITHUB (ZIP) — CHI MAY B / PC KHONG CO .git
#
# MAY A (C:\Users\thais\ADMIN co .git): KHONG CHAY SCRIPT NAY.
#   cd C:\Users\thais\ADMIN
#   git pull origin cursor/drive-hourly-pipeline-df0f
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_GAP_ROI_HOURLY.ps1
#
# Script nay chi cho may khac khong co git (ZIP giai nen).
# GIU nguyen pipeline\config.local.json
# ============================================================

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path -LiteralPath (Join-Path $Repo ".git"))) {
  Write-Host "Khong co .git — tiep tuc cap nhat tu ZIP (may B / bootstrap)."
} else {
  Write-Host "PHAT HIEN .git — day la may A. KHONG dung CAP_NHAT_TU_GITHUB.ps1."
  Write-Host "Chay thay:"
  Write-Host "  git pull origin cursor/drive-hourly-pipeline-df0f"
  Write-Host "  powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_GAP_ROI_HOURLY.ps1"
  exit 0
}

if (-not (Test-Path -LiteralPath (Join-Path $Repo "pipeline"))) {
  $Repo = "C:\Users\Administrator\ADMIN"
}
Set-Location $Repo

$Branch = "cursor/drive-hourly-pipeline-df0f"
$ZipUrl = "https://github.com/thaison20101/ADMIN/archive/refs/heads/$Branch.zip"
$Tmp = Join-Path $env:TEMP "ADMIN_pipeline_update"
$Zip = Join-Path $env:TEMP "ADMIN_$Branch.zip"

Write-Host "Downloading ZIP (co the mat 1-2 phut)..."
if (Test-Path -LiteralPath $Tmp) { Remove-Item -LiteralPath $Tmp -Recurse -Force -ErrorAction SilentlyContinue }
if (Test-Path -LiteralPath $Zip) { Remove-Item -LiteralPath $Zip -Force -ErrorAction SilentlyContinue }
Invoke-WebRequest -Uri $ZipUrl -OutFile $Zip -UseBasicParsing
Expand-Archive -LiteralPath $Zip -DestinationPath $Tmp -Force
$Inner = Get-ChildItem -LiteralPath $Tmp -Directory | Select-Object -First 1
if (-not $Inner) { throw "ZIP empty" }
$SrcPipe = Join-Path $Inner.FullName "pipeline"
if (-not (Test-Path -LiteralPath $SrcPipe)) { throw "No pipeline/ in ZIP" }

$DestPipe = Join-Path $Repo "pipeline"
$CfgLocal = Join-Path $DestPipe "config.local.json"
$CfgBackup = Join-Path $env:TEMP "config.local.json.bak"
if (Test-Path -LiteralPath $CfgLocal) {
  Copy-Item -LiteralPath $CfgLocal -Destination $CfgBackup -Force
  Write-Host "Backed up config.local.json"
}

Write-Host "Copy pipeline/ ..."
Remove-Item -LiteralPath $DestPipe -Recurse -Force -ErrorAction SilentlyContinue
Copy-Item -LiteralPath $SrcPipe -Destination $DestPipe -Recurse -Force

if (Test-Path -LiteralPath $CfgBackup) {
  Copy-Item -LiteralPath $CfgBackup -Destination $CfgLocal -Force
  Write-Host "Restored config.local.json"
}

Write-Host "OK: pipeline updated from $Branch"
Write-Host "May B: cau hinh G:\Drive cua toi\PKDK_Thuankieu_Pipeline trong config.local.json neu can."
Remove-Item -LiteralPath $Tmp -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $Zip -Force -ErrorAction SilentlyContinue
exit 0
