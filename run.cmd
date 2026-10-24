@echo off
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONPATH=%~dp0src"

if exist "%~dp0.venv\Scripts\pythonw.exe" (
  start "" "%~dp0.venv\Scripts\pythonw.exe" -m campusrun gui
  exit /b 0
)
where pyw >nul 2>nul
if not errorlevel 1 (
  start "" pyw -3 -m campusrun gui
  exit /b 0
)
where py >nul 2>nul
if not errorlevel 1 (
  py -3 -m campusrun gui
  if errorlevel 1 pause
  exit /b
)
where python >nul 2>nul
if not errorlevel 1 (
  python -m campusrun gui
  if errorlevel 1 pause
  exit /b
)
echo [CampusRun] Python 3 not found.
echo Install Python 3.10+ from https://www.python.org/downloads/windows/
echo and enable "Add python.exe to PATH" during setup.
pause
exit /b 1
