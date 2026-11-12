#Requires -Version 7.0
<#
.SYNOPSIS
  PowerShell 7 front end for the ticalc Python CLI.
.DESCRIPTION
  Finds Python (or a repo-local .venv), installs ticalc on first use if needed,
  and forwards every argument to `python -m ticalc`. The exit code is passed through.
.EXAMPLE
  ./scripts/ticalc.ps1 programs tests/data/Actual.tns
  ./scripts/ticalc.ps1 encode my-code.txt --base Calculator.tns -o New.tns
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$root = Split-Path $PSScriptRoot -Parent
$python = @(
    (Join-Path $root '.venv/Scripts/python.exe'),
    (Join-Path $root '.venv/bin/python')
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $python) {
    $cmd = Get-Command python3, python -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $cmd) { Write-Error 'Python 3.10+ was not found on PATH. Install it from https://www.python.org/downloads/'; exit 2 }
    $python = $cmd.Source
}

& $python -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'
if ($LASTEXITCODE -ne 0) { Write-Error 'Python 3.10 or newer is required.'; exit 2 }

& $python -c 'import ticalc' 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host 'Installing ticalc (first run)...'
    & $python -m pip install --quiet $root
    if ($LASTEXITCODE -ne 0) { Write-Error 'pip install failed.'; exit 2 }
}

& $python -m ticalc @args
exit $LASTEXITCODE
