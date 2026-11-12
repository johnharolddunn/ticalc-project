#Requires -Version 7.0
<#
.SYNOPSIS
  Simple prompt-driven menu over the ticalc CLI (no need to remember commands).
#>
Set-StrictMode -Version Latest
$ticalc = Join-Path $PSScriptRoot 'ticalc.ps1'

function Read-Path([string]$Prompt) { (Read-Host $Prompt).Trim().Trim('"').Trim("'") }

while ($true) {
    Write-Host "`nTI-Nspire toolkit`n  1) Show a .tns summary`n  2) Print its programs/functions`n  3) Save programs/functions to a text file`n  4) Store a text file's programs into a copy of a .tns`n  5) Self-test a .tns (decode/rebuild/compare)`n  Q) Quit"
    switch ((Read-Host 'Choose').ToUpper()) {
        '1' { & $ticalc info (Read-Path 'Path to .tns') }
        '2' { & $ticalc programs (Read-Path 'Path to .tns') }
        '3' { $f = Read-Path 'Path to .tns'; & $ticalc programs $f -o (Read-Path 'Output .txt path') }
        '4' { $s = Read-Path 'Source .txt'; $b = Read-Path 'Base .tns (not modified)'; & $ticalc encode $s --base $b -o (Read-Path 'New .tns to write') }
        '5' { & $ticalc check (Read-Path 'Path to .tns or folder') }
        'Q' { return }
        default { Write-Host 'Please choose 1-5 or Q.' }
    }
}
