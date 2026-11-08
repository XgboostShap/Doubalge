@echo off
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
if not exist ".runtime\installation.json" goto missing
if not exist ".venv\Scripts\python.exe" goto missing
".venv\Scripts\python.exe" -X utf8 app_local.py
if errorlevel 1 pause
exit /b
:missing
echo Lancez d'abord Installer-Windows.cmd dans ce dossier.
pause
exit /b 1
