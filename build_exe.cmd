@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\build_exe.ps1"
if errorlevel 1 (
  echo Build failed.
  pause
  exit /b 1
)
echo Build finished. See dist\CampusRun-0.1.1-win64.zip
pause
