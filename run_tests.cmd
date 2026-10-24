@echo off
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONPATH=%~dp0src"

where py >nul 2>nul
if not errorlevel 1 (
  py -3 -m unittest discover -s tests -t . -v
  if errorlevel 1 pause
  exit /b
)
where python >nul 2>nul
if not errorlevel 1 (
  python -m unittest discover -s tests -t . -v
  if errorlevel 1 pause
  exit /b
)
echo [CampusRun] Python 3 not found.
pause
exit /b 1
