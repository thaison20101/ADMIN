# Force refill form VONG QUOC CHU (MCHC/RDW) — may A
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_REFILL_QUOC_CHU.ps1
#
# PDF lab thuong KHONG co CCCD trong text; file nam o TK2:
#   G:\Drive của tôi\PKDK_Thuankieu_Pipeline\TK2\300826-497079 - VONG QUOC CHU - 1987 - M.pdf

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
if (-not $Repo) { $Repo = "C:\Users\thais\ADMIN" }
Set-Location $Repo

$env:MEDINET_SSL_VERIFY = "0"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUNBUFFERED = "1"
$env:PYTHONUTF8 = "1"

. (Join-Path $PSScriptRoot "Resolve-PkdkPython.ps1")
$Python = Resolve-PkdkPython

Write-Host "=== REFILL QUOC CHU ==="

# Neu Google Drive dang pause — canh bao
Write-Host "NOTE: Neu Drive popup 'dong bo tam dung' -> bam 'Tiep tuc dong bo hoa'."

$PdfArg = @()
# Tim file theo ten (TK2 truoc) — khong doi CCCD trong PDF
$roots = @(
  "G:\Drive của tôi\PKDK_Thuankieu_Pipeline\TK2",
  "G:\Drive của tôi\PKDK_Thuankieu_Pipeline\TK1",
  "G:\Drive của tôi\PKDK_Thuankieu_Pipeline\ERROR",
  "G:\Drive của tôi\PKDK_Thuankieu_Pipeline\CCCD",
  "G:\Drive của tôi\PKDK_Thuankieu_Pipeline\PROCESSED",
  "G:\Drive của tôi\PKDK_Thuankieu_Pipeline\MISSING"
)
$found = $null
foreach ($r in $roots) {
  if (-not (Test-Path -LiteralPath $r)) { continue }
  $hit = Get-ChildItem -LiteralPath $r -Filter "*VONG*QUOC*CHU*.pdf" -File -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
  if (-not $hit) {
    $hit = Get-ChildItem -LiteralPath $r -Filter "*Vong*Quoc*Chu*.pdf" -Recurse -File -ErrorAction SilentlyContinue |
      Sort-Object LastWriteTime -Descending |
      Select-Object -First 1
  }
  if ($hit) {
    $found = $hit.FullName
    Write-Host ("PDF found: " + $found)
    break
  }
}

if ($found) {
  $PdfArg = @("--pdf", $found)
} else {
  Write-Host "WARN: PS1 khong thay *VONG*QUOC*CHU*.pdf — de Python tu quet"
}

& $Python ".\pipeline\refill_one_patient.py" @PdfArg @args
exit $LASTEXITCODE
