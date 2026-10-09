# Resolve absolute python.exe for Task Scheduler (PATH often missing python).
# Dot-source: . .\pipeline\Resolve-PkdkPython.ps1
# Then: $Python = Resolve-PkdkPython

function Resolve-PkdkPython {
  if ($env:PKDK_PYTHON -and (Test-Path -LiteralPath $env:PKDK_PYTHON)) {
    return $env:PKDK_PYTHON
  }
  try {
    $hint = Join-Path $PSScriptRoot "work\pkdk_python.txt"
    if (Test-Path -LiteralPath $hint) {
      $p = (Get-Content -LiteralPath $hint -Encoding UTF8 -Raw).Trim()
      if ($p -and (Test-Path -LiteralPath $p)) { return $p }
    }
  } catch {}
  try {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source -and (Test-Path -LiteralPath $cmd.Source)) {
      return $cmd.Source
    }
  } catch {}
  try {
    $out = & py -3 -c "import sys; print(sys.executable)" 2>$null
    if ($out) {
      $p = ([string]$out).Trim()
      if ($p -and (Test-Path -LiteralPath $p)) { return $p }
    }
  } catch {}
  try {
    $cmd = Get-Command py -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source) { return $cmd.Source }
  } catch {}
  return "python"
}
