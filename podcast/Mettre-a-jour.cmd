@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -STA -File "%~dp0mettre-a-jour.ps1"
if errorlevel 1 (
  echo.
  echo Mise a jour interrompue. Vos projets n'ont pas ete modifies.
  pause
  exit /b 1
)
