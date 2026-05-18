@echo off
setlocal

cd /d "%~dp0"

REM Store the virtual environment outside the project folder to avoid Windows long-path errors with PySide6.
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
    echo.
    echo If you previously saw a Windows long-path error, this version uses a shorter shared virtual environment path.
    echo You can also move the project folder to C:\app if needed.
    pause
    exit /b 1
)

"%VENV_DIR%\Scripts\python.exe" app.py
if errorlevel 1 (
    echo The app exited with an error.
    pause
    exit /b 1
)

endlocal
