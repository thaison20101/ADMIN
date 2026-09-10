# Force refill form VONG QUOC CHU (MCHC/RDW) - may A
# ASCII-only (Windows PowerShell 5.x breaks on UTF-8 Vietnamese in .ps1)
#
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_REFILL_QUOC_CHU.ps1
#
# PDF lab often has NO CCCD in text; file is under TK2:
#   G:\Drive cua toi\PKDK_Thuankieu_Pipeline\TK2\*VONG*QUOC*CHU*.pdf

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
Write-Host "NOTE: If Drive popup says sync paused, click Continue sync."

$PdfArg = @()
# Try ASCII + Unicode path variants (Drive folder name differs by locale)
$pipeRoots = @(
  "G:\Drive cua toi\PKDK_Thuankieu_Pipeline",
  "G:\My Drive\PKDK_Thuankieu_Pipeline",
  "G:\PKDK_Thuankieu_Pipeline"
)
# Also resolve live root from Python (handles "Drive cua toi" unicode)
try {
  $pyRoot = & $Python -c "from drive_paths import discover_pipeline_root; print(discover_pipeline_root())"
  if ($pyRoot -and (Test-Path -LiteralPath $pyRoot)) {
    $pipeRoots = @($pyRoot) + $pipeRoots
  }
} catch {
  Write-Host "WARN: could not resolve pipeline root via Python"
}

$subFolders = @("TK2", "TK1", "ERROR", "CCCD", "PROCESSED", "MISSING", "INBOX_CLS")
$found = $null
foreach ($base in $pipeRoots) {
  if (-not (Test-Path -LiteralPath $base)) { continue }
  Write-Host ("scan base: " + $base)
  foreach ($sub in $subFolders) {
    $r = Join-Path $base $sub
    if (-not (Test-Path -LiteralPath $r)) { continue }
    $hit = Get-ChildItem -LiteralPath $r -Filter "*VONG*QUOC*CHU*.pdf" -File -ErrorAction SilentlyContinue |
      Sort-Object LastWriteTime -Descending |
      Select-Object -First 1
    if (-not $hit) {
      $hit = Get-ChildItem -LiteralPath $r -Filter "*Vong*Quoc*Chu*.pdf" -File -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    }
    if ($hit) {
      $found = $hit.FullName
      Write-Host ("PDF found: " + $found)
      break
    }
  }
  if ($found) { break }
}

if ($found) {
  $PdfArg = @("--pdf", $found)
} else {
  Write-Host "WARN: PS1 did not find *VONG*QUOC*CHU*.pdf - Python will scan"
}

& $Python ".\pipeline\refill_one_patient.py" @PdfArg
$code = $LASTEXITCODE
exit $code
