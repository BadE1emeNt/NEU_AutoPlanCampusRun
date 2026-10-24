# Build the Windows one-folder release.
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File tools\build_exe.ps1

param(
    [string]$Python = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not $Python) {
    $commands = @("py", "python")
    foreach ($name in $commands) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) {
            $Python = $cmd.Source
            break
        }
    }
}
if (-not $Python) {
    throw "Python 3.10+ not found. Install Python and run again."
}

$venv = Join-Path $root ".venv-build"
$venvPython = Join-Path $venv "Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    & $Python -m venv $venv
}

& $venvPython -m pip install --disable-pip-version-check -r packaging\requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

& $venvPython -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name CampusRun `
    --paths src `
    --distpath dist `
    --workpath build\pyinstaller `
    packaging\launcher.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$release = Join-Path $root "dist\CampusRun"
Copy-Item README.md (Join-Path $release "README.md") -Force
Copy-Item docs\CAPTURE.md (Join-Path $release "CAPTURE.md") -Force
Copy-Item docs\screenshot-dashboard.png (Join-Path $release "screenshot-dashboard.png") -Force

$zip = Join-Path $root "dist\CampusRun-0.1.0-win64.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path $release -DestinationPath $zip
Get-FileHash $zip -Algorithm SHA256 | Format-List

Write-Host "Built: $zip"
