# Soak test (M7): run the full default suite N times, each in a fresh process with fault logging.
# A run that crashes keeps its full log; the summary lists exit codes and the last test started.
# Usage:  powershell -File tools\soak.ps1 -Runs 20 -Out <folder>
param([int]$Runs = 20, [string]$Out = "soak-logs")

$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
New-Item -ItemType Directory -Force $Out | Out-Null
$summary = Join-Path $Out "summary.txt"
"run,exit,seconds,result,last_test" | Set-Content $summary -Encoding utf8
for ($i = 1; $i -le $Runs; $i++) {
    $log = Join-Path $Out ("run{0:D2}.txt" -f $i)
    $started = Get-Date
    Push-Location $root
    & $python -X faulthandler -m pytest -v -p no:cacheprovider *> $log
    $code = $LASTEXITCODE
    Pop-Location
    $seconds = [int]((Get-Date) - $started).TotalSeconds
    $lines = Get-Content $log
    $result = ($lines | Select-String "passed|failed" | Select-Object -Last 1).Line
    $last = ($lines | Select-String "^tests/.*::" | Select-Object -Last 1).Line
    "$i,$code,$seconds,""$result"",""$last""" | Add-Content $summary -Encoding utf8
    "run $i exit $code ($seconds s) $result"
}
