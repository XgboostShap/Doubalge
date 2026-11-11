@echo off
setlocal
cd /d "%~dp0"
if not exist "%~dp0.venv\Scripts\python.exe" (
  echo Lancez d'abord Installer-Windows.cmd.
  pause
  exit /b 1
)
set "PYTHONIOENCODING=utf-8"
set "PYTHONDONTWRITEBYTECODE=1"
"%~dp0.venv\Scripts\python.exe" -c "import pypdf" >nul 2>&1
if errorlevel 1 (
  echo Relancez Installer-Windows.cmd pour terminer l'installation.
  pause
  exit /b 1
)
"%~dp0.venv\Scripts\python.exe" "%~dp0app.py"
if errorlevel 1 pause
