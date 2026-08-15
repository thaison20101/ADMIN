# ============================================================
# CAP NHAT CODE TU GITHUB (khong can .git)
#
# Dung khi: "fatal: not a git repository" / thieu file .ps1 moi
# Tai ZIP nhanh cursor/drive-hourly-pipeline-df0f, ghi de pipeline/
# GIU nguyen pipeline\config.local.json
#
#   cd C:\Users\Administrator\ADMIN
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CAP_NHAT_TU_GITHUB.ps1
#
# Neu CHUA co file nay: copy-paste toan bo lenh trong comment cuoi file,
# hoac chay block "BOOTSTRAP" ben duoi bang tay.
# ============================================================

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path -LiteralPath (Join-Path $Repo "pipeline"))) {
  $Repo = "C:\Users\Administrator\ADMIN"
}
Set-Location $Repo

$Branch = "cursor/drive-hourly-pipeline-df0f"
$ZipUrl = "https://github.com/thaison20101/ADMIN/archive/refs/heads/$Branch.zip"
$Tmp = Join-Path $env:TEMP "ADMIN_pipeline_update"
$Zip = Join-Path $env:TEMP "ADMIN_$Branch.zip"
$CfgKeep = Join-Path $Repo "pipeline\config.local.json"
$CfgBak = Join-Path $env:TEMP "config.local.json.bak_pkdk"

Write-Host "Repo: $Repo"
Write-Host "Tai:  $ZipUrl"

if (Test-Path -LiteralPath $CfgKeep) {
  Copy-Item -LiteralPath $CfgKeep -Destination $CfgBak -Force
  Write-Host "Backup config -> $CfgBak"
}

if (Test-Path -LiteralPath $Tmp) { Remove-Item -LiteralPath $Tmp -Recurse -Force }
New-Item -ItemType Directory -Force -Path $Tmp | Out-Null

Write-Host "Downloading ZIP (co the mat 1-2 phut)..."
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Invoke-WebRequest -Uri $ZipUrl -OutFile $Zip -UseBasicParsing

Write-Host "Expand..."
Expand-Archive -LiteralPath $Zip -DestinationPath $Tmp -Force
$Inner = Get-ChildItem -LiteralPath $Tmp -Directory | Select-Object -First 1
if (-not $Inner) { throw "ZIP empty" }

Write-Host "Copy pipeline + tracking scripts tu: $($Inner.FullName)"
$SrcPipe = Join-Path $Inner.FullName "pipeline"
if (-not (Test-Path -LiteralPath $SrcPipe)) { throw "No pipeline/ in ZIP" }

# Ghi de toan bo file trong pipeline (tru config.local.json)
Get-ChildItem -LiteralPath $SrcPipe -File | ForEach-Object {
  if ($_.Name -ieq "config.local.json") { return }
  Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $Repo "pipeline\$($_.Name)") -Force
}
# subfolders neu co
Get-ChildItem -LiteralPath $SrcPipe -Directory -ErrorAction SilentlyContinue | ForEach-Object {
  $dest = Join-Path $Repo "pipeline\$($_.Name)"
  if (Test-Path -LiteralPath $dest) { Remove-Item -LiteralPath $dest -Recurse -Force }
  Copy-Item -LiteralPath $_.FullName -Destination $dest -Recurse -Force
}

if (Test-Path -LiteralPath $CfgBak) {
  Copy-Item -LiteralPath $CfgBak -Destination $CfgKeep -Force
  Write-Host "Restore config.local.json"
}

Write-Host "Kiem tra file moi:"
Get-Item -LiteralPath (Join-Path $Repo "pipeline\CHAY_KIEM_1_LAN_TOAN_BO.ps1") | Format-List Name, Length, LastWriteTime

Write-Host ""
Write-Host "OK. Tiep theo chay:"
Write-Host "  powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_KIEM_1_LAN_TOAN_BO.ps1"
Write-Host "  (script do se git pull - neu khong co .git thi bo qua loi git, van full-scan duoc)"
