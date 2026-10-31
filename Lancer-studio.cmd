@echo off
setlocal
set "PYTHONUTF8=1"
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Executez d'abord Installer-studio.cmd.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -X utf8 -u studio\lancer_studio.py
set "STUDIO_RESULT=%ERRORLEVEL%"
if not "%STUDIO_RESULT%"=="0" echo Le traitement a echoue. Conservez le message ci-dessus.
pause
exit /b %STUDIO_RESULT%
