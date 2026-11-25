<#
.SYNOPSIS
  Starts HX Edit Unbound with everything on (run .\setup.ps1 once before).

.PARAMETER DryRun
  Only show the command that would start it; nothing is started.

.EXAMPLE
  .\start.ps1
.EXAMPLE
  .\start.ps1 -DryRun
#>
[CmdletBinding()]
param([switch]$DryRun)

$ErrorActionPreference = 'Stop'
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Pythonw = Join-Path $Here '.venv\Scripts\pythonw.exe'
$Launcher = Join-Path $Here 'src\start-hx-edit-nam.pyw'
$Arguments = @("`"$Launcher`"", '--unbound')

if (-not (Test-Path -LiteralPath $Pythonw)) {
  Write-Host 'HX Edit Unbound is not set up yet. Run .\setup.ps1 first.' -ForegroundColor Yellow
  exit 1
}
if ($DryRun) {
  Write-Host "Would start: `"$Pythonw`" $($Arguments -join ' ')"
  exit 0
}
$open = Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('HX Edit', 'HX Edit NAM') }
if ($open) {
  Write-Host 'HX Edit is open. Close it, then run .\start.ps1 again.' -ForegroundColor Yellow
  exit 1
}

# Started without a console window; what it writes to its error output is kept, to show it if it stops at once.
$errors = Join-Path $env:TEMP 'hx-edit-unbound-start.txt'
$process = Start-Process -FilePath $Pythonw -ArgumentList $Arguments -WorkingDirectory $Here -PassThru `
  -RedirectStandardError $errors
Write-Host 'Starting HX Edit Unbound...'
if (-not $process.WaitForExit(8000)) {
  Write-Host 'HX Edit Unbound is starting (HX Edit opens in a moment).'
  exit 0
}
if ($process.ExitCode -eq 0) { exit 0 }
Write-Host "HX Edit Unbound stopped at once (exit code $($process.ExitCode))." -ForegroundColor Yellow
if ((Test-Path -LiteralPath $errors) -and (Get-Item -LiteralPath $errors).Length -gt 0) {
  Get-Content -LiteralPath $errors -Tail 20 | ForEach-Object { Write-Host "  $_" }
}
exit 1
