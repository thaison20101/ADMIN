# ============================================================
# BO SUNG FIELD TU PDF LEN WEB — CHI INBOX + ERROR + PROCESSED
# (MISSING = chua TTHC -> khong dien duoc Ure/field; quet 10k MISSING lam G: chet)
#
#   cd C:\Users\thais\ADMIN
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_BO_SUNG_THIEU.ps1
# ============================================================

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
Set-Location $Repo

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUNBUFFERED = "1"
if (-not $env:MEDINET_USER) { $env:MEDINET_USER = "pkdk_Thuankieu" }
if (-not $env:MEDINET_PASS) { $env:MEDINET_PASS = "pkdk_Thuankieu#2026" }
try {
  [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
  $OutputEncoding = [System.Text.UTF8Encoding]::new($false)
} catch {}

Write-Host ""
Write-Host "############################################################"
Write-Host "#  BO SUNG Ure/field: INBOX+ERROR+PROCESSED (khong MISSING) #"
Write-Host "############################################################"

Write-Host "==== 1/3 git pull ===="
if (Test-Path -LiteralPath (Join-Path $Repo ".git")) {
  git pull origin cursor/drive-hourly-pipeline-df0f
}

Write-Host "==== 2/3 config + assert G: ===="
& python ".\pipeline\ensure_config.py"
& python -m pip install -q -r ".\pipeline\requirements.txt"
& python ".\pipeline\assert_g_pipeline.py"
if ($LASTEXITCODE -ne 0) {
  Write-Host "DUNG: G: chua san. Mo Google Drive Desktop roi chay lai."
  exit 2
}

Write-Host "==== 3/3 REPAIR INBOX+ERROR+PROCESSED (Ure neu PDF co) ===="
Write-Host "Khong full-scan MISSING (11k file lam G: unmount)."
$code = 0
for ($round = 1; $round -le 3; $round++) {
  Write-Host ("----- VONG {0}/3 -----" -f $round)
  & python ".\pipeline\assert_g_pipeline.py"
  if ($LASTEXITCODE -ne 0) {
    Write-Host "DUNG: G: mat ket noi giua vong. Mo Drive roi chay lai."
    exit 2
  }
  Write-Host ("hourly_sync --repair --missing-budget 0 (log live)")
  $outLines = New-Object System.Collections.Generic.List[string]
  & python -u ".\pipeline\hourly_sync.py" --repair --missing-budget 0 2>&1 | ForEach-Object {
    Write-Host $_
    [void]$outLines.Add("$_")
  }
  $code = $LASTEXITCODE
  $text = ($outLines -join "`n")
  if ($text -match "ABORT:") {
    Write-Host "DUNG: ABORT G:. Khong bat hourly."
    exit 2
  }
  $statLine = $text | & python ".\pipeline\parse_cycle_stats.py"
  $parts = @($statLine -split "\s+")
  $imported = 0; $queued = 0; $repair = 0
  if ($parts.Count -ge 6) {
    $imported = [int]$parts[0]
    $queued = [int]$parts[1]
    $repair = [int]$parts[5]
  }
  Write-Host ("Vong {0}: imported={1} repair={2} queued={3}" -f $round, $imported, $repair, $queued)
  & python ".\pipeline\print_drive_dirs.py" | Select-Object -Last 1 | ForEach-Object { Write-Host $_ }
  if (($repair -le 0) -and ($queued -le 0) -and ($imported -le 0) -and $round -ge 2) { break }
}

Write-Host ""
Write-Host "========== XONG BO SUNG =========="
Write-Host "Ure: chi dien khi PDF co Urea. MISSING van cho TTHC (khong dien duoc)."
Write-Host "=================================="
if ($code -ne 0) { exit $code }
exit 0
