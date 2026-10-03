@echo off
setlocal
cd /d "%~dp0"

REM Build a portable Windows application folder for Almiqs AlBaseet.
REM Internal folder/exe names are ASCII to avoid encoding/path problems.

set "VENV_DIR=%USERPROFILE%\almiqs-albaseet-build-venv"
set "YOUTUBE_RUNTIME_DIR=%VENV_DIR%\youtube-runtime"
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
if errorlevel 1 (
    echo Failed to update pip.
    pause
    exit /b 1
)

REM YouTube changes frequently. Refresh yt-dlp nightly and its default extras
REM (including yt-dlp-ejs) on every release build instead of reusing a stale copy.
"%VENV_DIR%\Scripts\python.exe" -m pip install --upgrade --pre "yt-dlp[default]"
if errorlevel 1 (
    echo Failed to update yt-dlp nightly.
    pause
    exit /b 1
)

"%VENV_DIR%\Scripts\python.exe" -m pip install -r requirements-build.txt
if errorlevel 1 (
    echo Failed to install build requirements.
    pause
    exit /b 1
)

"%VENV_DIR%\Scripts\python.exe" -m pip check
if errorlevel 1 (
    echo Python dependency check failed.
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\prepare_youtube_runtime.ps1" -DestinationDir "%YOUTUBE_RUNTIME_DIR%"
if errorlevel 1 (
    echo Failed to prepare the Deno runtime required for full YouTube support.
    pause
    exit /b 1
)

rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul

"%VENV_DIR%\Scripts\pyinstaller.exe" --noconfirm --clean --windowed ^
  --name "AlmiqsAlBaseet" ^
  --icon "assets\icon.ico" ^
  --add-data "assets;assets" ^
  --collect-all "yt_dlp_ejs" ^
  app.py

if errorlevel 1 (
    echo Build failed.
    pause
    exit /b 1
)

REM Bundle external runtimes beside the exe and in bin so yt-dlp/subprocess can find them.
mkdir "%~dp0dist\AlmiqsAlBaseet\bin" 2>nul
if exist "%~dp0tools\ffmpeg.exe" (
    copy /y "%~dp0tools\ffmpeg.exe" "%~dp0dist\AlmiqsAlBaseet\ffmpeg.exe" >nul
    copy /y "%~dp0tools\ffmpeg.exe" "%~dp0dist\AlmiqsAlBaseet\bin\ffmpeg.exe" >nul
) else (
    echo WARNING: tools\ffmpeg.exe was not found. YouTube best-quality merge may fail on team devices.
)

if exist "%YOUTUBE_RUNTIME_DIR%\deno.exe" (
    copy /y "%YOUTUBE_RUNTIME_DIR%\deno.exe" "%~dp0dist\AlmiqsAlBaseet\deno.exe" >nul
    copy /y "%YOUTUBE_RUNTIME_DIR%\deno.exe" "%~dp0dist\AlmiqsAlBaseet\bin\deno.exe" >nul
) else (
    echo ERROR: deno.exe was not prepared. Full YouTube support cannot be guaranteed.
    pause
    exit /b 1
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
