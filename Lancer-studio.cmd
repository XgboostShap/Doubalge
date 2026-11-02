@echo off
setlocal
set "PYTHONUTF8=1"
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Executez d'abord Installer-studio.cmd.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -c "import webview" >nul 2>&1
if errorlevel 1 (
  echo Installation de la fenetre Doubalge...
  ".venv\Scripts\python.exe" -m pip install -r studio\requirements-app.txt
  if errorlevel 1 (
    echo Installation interrompue. Conservez le message ci-dessus.
    pause
    exit /b 1
  )
)
start "" ".venv\Scripts\pythonw.exe" -X utf8 studio\application.py
exit /b 0
