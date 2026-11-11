@echo off
setlocal
cd /d "%~dp0"
echo Installation de Podcast pedagogique dans ce dossier.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer.ps1"
if errorlevel 1 (
  echo.
  echo L'installation n'a pas abouti. Le detail est affiche ci-dessus.
  pause
  exit /b 1
)
echo.
echo Installation terminee. Ouvrez Lancer-Podcast.cmd.
pause
