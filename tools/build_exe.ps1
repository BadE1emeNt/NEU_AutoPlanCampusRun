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

New-Item -ItemType Directory -Force "build\pyinstaller" | Out-Null
& $venvPython -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name CampusRun `
    --paths src `
    --specpath "build\pyinstaller" `
    --distpath dist `
    --workpath build\pyinstaller `
    packaging\launcher.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$release = Join-Path $root "dist\CampusRun"
Copy-Item README.md (Join-Path $release "README.md") -Force
Copy-Item README.dev.md (Join-Path $release "README.dev.md") -Force
Copy-Item LICENSE (Join-Path $release "LICENSE") -Force
Copy-Item DISCLAIMER.md (Join-Path $release "DISCLAIMER.md") -Force
$docsRelease = Join-Path $release "docs"
New-Item -ItemType Directory -Force $docsRelease | Out-Null
foreach ($name in @("CAPTURE.md", "API-NOTES.md", "LOGIN-NOTES.md", "PACKAGING.md", "screenshot-dashboard.png", "screenshot-account.png", "screenshot-records.png")) {
    if (Test-Path (Join-Path "docs" $name)) {
        Copy-Item (Join-Path "docs" $name) (Join-Path $docsRelease $name) -Force
    }
}

$zip = Join-Path $root "dist\CampusRun-0.1.1-win64.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path $release -DestinationPath $zip
Get-FileHash $zip -Algorithm SHA256 | Format-List

Write-Host "Built: $zip"
