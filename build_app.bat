@echo off
setlocal
cd /d "%~dp0"

REM Build a portable Windows application folder for Almiqs AlBaseet.
REM Internal folder/exe names are ASCII to avoid encoding/path problems.

set "VENV_DIR=%USERPROFILE%\almiqs-albaseet-build-venv"
set "PYTHON_CMD=python"
where py >nul 2>nul
if not errorlevel 1 set "PYTHON_CMD=py -3"

if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo Creating build virtual environment in: %VENV_DIR%
    %PYTHON_CMD% -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo Failed to create build virtual environment. Make sure Python is installed and available in PATH.
        pause
        exit /b 1
    )
)

"%VENV_DIR%\Scripts\python.exe" -m pip install --upgrade pip
"%VENV_DIR%\Scripts\python.exe" -m pip install -r requirements-build.txt
if errorlevel 1 (
    echo Failed to install build requirements.
    pause
    exit /b 1
)

rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul

"%VENV_DIR%\Scripts\pyinstaller.exe" --noconfirm --clean --windowed ^
  --name "AlmiqsAlBaseet" ^
  --icon "assets\icon.ico" ^
  --add-data "assets;assets" ^
  app.py

if errorlevel 1 (
    echo Build failed.
    pause
    exit /b 1
)

REM Bundle ffmpeg beside the exe and in bin so yt-dlp/subprocess can find it.
if exist "%~dp0tools\ffmpeg.exe" (
    copy /y "%~dp0tools\ffmpeg.exe" "%~dp0dist\AlmiqsAlBaseet\ffmpeg.exe" >nul
    mkdir "%~dp0dist\AlmiqsAlBaseet\bin" 2>nul
    copy /y "%~dp0tools\ffmpeg.exe" "%~dp0dist\AlmiqsAlBaseet\bin\ffmpeg.exe" >nul
) else (
    echo WARNING: tools\ffmpeg.exe was not found. YouTube best-quality merge may fail on team devices.
)

echo.
echo ================================
echo Build completed successfully.
echo Portable app folder:
echo dist\AlmiqsAlBaseet
echo.
echo Send the full dist\AlmiqsAlBaseet folder to the team.
echo Do not move only the EXE.
echo ================================
explorer "dist\AlmiqsAlBaseet"
pause
endlocal
