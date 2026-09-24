# DEPRECATED - rule cu (ho+ten+nam sinh, 1 TK) SAI.
# Chuyen sang CHAY_TONG_HOP_MOI.ps1 (rule moi + 2 TK dual-write).
#
#   cd C:\Users\thais\ADMIN
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_TONG_HOP_MOI.ps1

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
if (-not $Repo) { $Repo = "C:\Users\thais\ADMIN" }
Set-Location $Repo

Write-Host "############################################################"
Write-Host "#  SCRIPT CU DA BO - KHONG dung rule ho+ten+nam sinh        #"
Write-Host "#  Dang chuyen sang CHAY_TONG_HOP_MOI.ps1 (rule moi)        #"
Write-Host "############################################################"
Write-Host "Rule dung:"
Write-Host "  Match: ho+ten DAY DU + nam/SDT/CCCD | dual-write 2 TK"
Write-Host "  Route: 2TK+FULL->PROCESSED/U18 | 1TK+FULL->TK1/TK2"
Write-Host "         PARTIAL/OTHER->ERROR | noTTHC->MISSING | trung ten->UNDER18"

& powershell -ExecutionPolicy Bypass -File ".\pipeline\CHAY_TONG_HOP_MOI.ps1" @args
exit $LASTEXITCODE
