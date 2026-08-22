# Cap nhat file theo doi len G:\Drive cua toi\build for Supper Data
#   cd C:\Users\thais\ADMIN
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CAP_NHAT_TIEN_DO_SUPER_DATA.ps1

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
Set-Location $Repo

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

& python ".\pipeline\assert_g_pipeline.py"
if ($LASTEXITCODE -ne 0) {
  Write-Host "G: chua mount — chi ghi local pipeline\work\build"
}

& python ".\pipeline\super_data_status.py" --publish
& python ".\pipeline\print_counts.py" | ForEach-Object { Write-Host $_ }

Write-Host ""
Write-Host "Theo doi tren G:"
Write-Host "  G:\Drive cua toi\build for Supper Data\TIEN_DO_THEO_DOI.txt"
Write-Host "  G:\Drive cua toi\build for Supper Data\last_counts.txt"
Write-Host "  G:\Drive cua toi\build for Supper Data\logs\LAST_HOURLY_OK.txt"
