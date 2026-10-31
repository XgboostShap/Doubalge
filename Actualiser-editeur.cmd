@echo off
setlocal
set "PYTHONUTF8=1"
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Placez ce fichier et le dossier studio a cote de votre .venv existant.
  echo Ou executez d'abord Installer-studio.cmd.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -X utf8 studio\actualiser_editeur.py %*
if errorlevel 1 pause
