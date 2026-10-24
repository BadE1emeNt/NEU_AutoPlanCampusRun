@echo off
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONPATH=%~dp0src"

where py >nul 2>nul
if not errorlevel 1 (
  py -3 -m campusrun %*
  exit /b %errorlevel%
)
where python >nul 2>nul
if not errorlevel 1 (
  python -m campusrun %*
  exit /b %errorlevel%
)
echo [CampusRun] Python 3 not found.
echo Install Python 3.10+ and enable "Add python.exe to PATH".
exit /b 1
