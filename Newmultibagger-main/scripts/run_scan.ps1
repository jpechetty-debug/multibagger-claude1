# Launch a full universe scan as a detached process so it survives the terminal or
# agent session that started it (a scan takes ~75 min; shells get torn down sooner).
# Logs go to runtime/scan_<timestamp>.log/.err; the DQ audit result is at the end of
# the log, and the process exit code is 1 when the audit fails.
#
# Usage (from Newmultibagger-main):  powershell -File scripts/run_scan.ps1 [extra screener args]

$root = Split-Path -Parent $PSScriptRoot
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$log = Join-Path $root "runtime\scan_$stamp.log"
$env:PYTHONIOENCODING = "utf-8"

$proc = Start-Process -FilePath (Join-Path $root ".venv\Scripts\python.exe") `
    -ArgumentList (@("-u", "scripts\internal\screener.py") + $args) `
    -WorkingDirectory $root `
    -RedirectStandardOutput $log `
    -RedirectStandardError ($log -replace "\.log$", ".err") `
    -WindowStyle Hidden -PassThru

Write-Output "Scan started: PID $($proc.Id), log $log"
