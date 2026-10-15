# Create Desktop shortcuts. Primary = chay nhu truoc (hourly ON).
# ASCII-only.
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
  $s.Arguments = '-NoExit -NoProfile -ExecutionPolicy Bypass -File "' + $TargetPs1 + '"'
  $s.WorkingDirectory = $Repo
  $s.WindowStyle = 1
  $s.Description = $Description
  $s.Save()
  Write-Host ("OK shortcut: " + $lnkPath)
}

$main = Join-Path $PSScriptRoot "CHAY_LAI_NHU_TRUOC.ps1"
$pause = Join-Path $PSScriptRoot "NUT_TAM_DUNG_HOURLY.ps1"
$inboxOnce = Join-Path $PSScriptRoot "NUT_CHAY_INBOX_1_LAN.ps1"

New-PkdkShortcut -Name "PKDK - Chay lai nhu truoc" -TargetPs1 $main -Description "Hourly ON + fill INBOX (default, no pause)"
New-PkdkShortcut -Name "PKDK - Tam dung hourly" -TargetPs1 $pause -Description "Optional pause only"
New-PkdkShortcut -Name "PKDK - Chay INBOX 1 lan" -TargetPs1 $inboxOnce -Description "One inbox pass"

Write-Host ""
Write-Host "Desktop: dung 'PKDK - Chay lai nhu truoc' de bat dien web."
Write-Host ("Desktop: " + $Desktop)
exit 0
