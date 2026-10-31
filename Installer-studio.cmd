@echo off
setlocal
set "PYTHONUTF8=1"
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto dependencies
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
  "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" -m venv .venv
) else (
  py -3.12 -m venv .venv
)
if errorlevel 1 goto python_error
:dependencies
set "STUDIO_BUILD=cu128"
if /i "%~1"=="cpu" set "STUDIO_BUILD=cpu"
".venv\Scripts\python.exe" -m pip install "torch==2.8.0+%STUDIO_BUILD%" "torchaudio==2.8.0+%STUDIO_BUILD%" --index-url https://download.pytorch.org/whl/%STUDIO_BUILD%
if errorlevel 1 goto error
".venv\Scripts\python.exe" -m pip install -r studio\requirements.txt
if errorlevel 1 goto error
".venv\Scripts\python.exe" -m pip check
if errorlevel 1 goto error
echo Installation terminee. Ouvrez Lancer-studio.cmd.
pause
exit /b 0
:python_error
echo Installez Python 3.12 64 bits ou creez .venv avec votre Python Conda 3.12.
pause
exit /b 1
:error
echo Installation interrompue. Conservez le message ci-dessus.
pause
exit /b 1
