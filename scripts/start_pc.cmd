@echo off
setlocal

rem Always launch from the repository root, independently of the shortcut's CWD.
for %%I in ("%~dp0..") do set "REPO_ROOT=%%~fI"
cd /d "%REPO_ROOT%"

set "PYTHON_EXE="
if exist "%REPO_ROOT%\.venv\Scripts\python.exe" set "PYTHON_EXE=%REPO_ROOT%\.venv\Scripts\python.exe"
if not defined PYTHON_EXE if exist "%REPO_ROOT%\venv\Scripts\python.exe" set "PYTHON_EXE=%REPO_ROOT%\venv\Scripts\python.exe"
if not defined PYTHON_EXE set "PYTHON_EXE=python"

echo Starting pyTrainer from %REPO_ROOT%
"%PYTHON_EXE%" -m kivy_app
if not errorlevel 1 goto :success
set "EXIT_CODE=%ERRORLEVEL%"
echo.
echo pyTrainer could not be started. Exit code: %EXIT_CODE%
pause
exit /b %EXIT_CODE%

:success
endlocal
