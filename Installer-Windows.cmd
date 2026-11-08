@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0installation-windows.ps1" %*
if errorlevel 1 goto error
echo.
echo Ouvrez Lancer-DoublageBasic.cmd pour commencer.
pause
exit /b 0
:error
echo Installation interrompue. Le message ci-dessus indique la cause.
pause
exit /b 1
