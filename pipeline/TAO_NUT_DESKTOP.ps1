# Create Desktop shortcuts (buttons) for pause / resume hourly.
# ASCII-only for Windows PowerShell 5.1
#
#   powershell -ExecutionPolicy Bypass -File .\pipeline\TAO_NUT_DESKTOP.ps1

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
$Desktop = [Environment]::GetFolderPath("Desktop")
if (-not $Desktop) { $Desktop = Join-Path $env:USERPROFILE "Desktop" }

function New-PkdkShortcut {
  param(
    [string]$Name,
    [string]$TargetPs1,
    [string]$Description
  )
  $lnkPath = Join-Path $Desktop ($Name + ".lnk")
  $w = New-Object -ComObject WScript.Shell
  $s = $w.CreateShortcut($lnkPath)
  $s.TargetPath = "powershell.exe"
  # Keep window open so user sees result (not a flash-close)
  $s.Arguments = '-NoExit -NoProfile -ExecutionPolicy Bypass -File "' + $TargetPs1 + '"'
  $s.WorkingDirectory = $Repo
  $s.WindowStyle = 1
  $s.Description = $Description
  $s.Save()
  Write-Host ("OK shortcut: " + $lnkPath)
}

$pause = Join-Path $PSScriptRoot "NUT_TAM_DUNG_HOURLY.ps1"
$resume = Join-Path $PSScriptRoot "NUT_BAT_LAI_KHI_CO_INBOX.ps1"
$inboxOnce = Join-Path $PSScriptRoot "NUT_CHAY_INBOX_1_LAN.ps1"

New-PkdkShortcut -Name "PKDK - Tam dung hourly" -TargetPs1 $pause -Description "Pause schedule only. Scan/fill rules UNCHANGED."
New-PkdkShortcut -Name "PKDK - Bat lai khi co INBOX" -TargetPs1 $resume -Description "Resume hourly with SAME scan/fill rules + 1 inbox pass"
New-PkdkShortcut -Name "PKDK - Chay INBOX 1 lan" -TargetPs1 $inboxOnce -Description "One inbox pass; leave hourly paused"

Write-Host ""
Write-Host "Desktop buttons created. Double-click when ready."
Write-Host ("Desktop: " + $Desktop)
exit 0
