@echo off
setlocal

cd /d "%~dp0"

REM Use the same short-path virtual environment as run_app.bat.
set "VENV_DIR=%USERPROFILE%\almiqs-albaseet-venv"

set "PYTHON_CMD=python"
where py >nul 2>nul
if not errorlevel 1 set "PYTHON_CMD=py -3"

if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo Creating virtual environment in: %VENV_DIR%
    %PYTHON_CMD% -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo Failed to create virtual environment. Make sure Python is installed and available in PATH.
        pause
        exit /b 1
    )
)

"%VENV_DIR%\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo Failed to install requirements.
    pause
    exit /b 1
)

"%VENV_DIR%\Scripts\python.exe" -m pytest
if errorlevel 1 (
    echo Tests failed.
    pause
    exit /b 1
)

pause
endlocal
