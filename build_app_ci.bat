@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

echo بدء بناء النسخة

set "VENV_DIR=%USERPROFILE%\almiqs-albaseet-build-venv"
set "YOUTUBE_RUNTIME_DIR=%VENV_DIR%\youtube-runtime"
set "PYTHON_CMD=python"
where py >nul 2>nul
if not errorlevel 1 set "PYTHON_CMD=py -3"
if defined ALMIQS_PYTHON set PYTHON_CMD="%ALMIQS_PYTHON%"

if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo Creating build virtual environment in: %VENV_DIR%
    %PYTHON_CMD% -m venv "%VENV_DIR%"
    if errorlevel 1 goto build_failed
)

"%VENV_DIR%\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto build_failed

REM Keep the embedded YouTube extractor fresh for release builds.
"%VENV_DIR%\Scripts\python.exe" -m pip install --upgrade --pre "yt-dlp[default]"
if errorlevel 1 goto build_failed

"%VENV_DIR%\Scripts\python.exe" -m pip install -r requirements-build.txt
if errorlevel 1 goto build_failed

"%VENV_DIR%\Scripts\python.exe" -m pip check
if errorlevel 1 goto build_failed

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\prepare_youtube_runtime.ps1" -DestinationDir "%YOUTUBE_RUNTIME_DIR%"
if errorlevel 1 goto build_failed

rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul

"%VENV_DIR%\Scripts\pyinstaller.exe" --noconfirm --clean --windowed ^
  --name "AlmiqsAlBaseet" ^
  --icon "%~dp0assets\icon.ico" ^
  --add-data "%~dp0assets;assets" ^
  --collect-all "yt_dlp" ^
  --collect-all "yt_dlp_ejs" ^
  --workpath "build" ^
  --specpath "build" ^
  --distpath "dist" ^
  app.py

if errorlevel 1 goto build_failed

if exist "%~dp0tools\ffmpeg.exe" (
    copy /y "%~dp0tools\ffmpeg.exe" "%~dp0dist\AlmiqsAlBaseet\ffmpeg.exe" >nul
) else (
    echo ERROR: tools\ffmpeg.exe was not found.
    goto build_failed
)

if exist "%YOUTUBE_RUNTIME_DIR%\deno.exe" (
    copy /y "%YOUTUBE_RUNTIME_DIR%\deno.exe" "%~dp0dist\AlmiqsAlBaseet\deno.exe" >nul
) else (
    echo deno.exe was not prepared.
    goto build_failed
)

if not exist "%~dp0RELEASE_README_AR.md" goto missing_release_readme
copy /y "%~dp0RELEASE_README_AR.md" "%~dp0dist\AlmiqsAlBaseet\README_AR.txt" >nul
if errorlevel 1 goto build_failed

if not exist "%~dp0dist\AlmiqsAlBaseet\AlmiqsAlBaseet.exe" goto build_failed
if not exist "%~dp0dist\AlmiqsAlBaseet\deno.exe" goto build_failed

"%VENV_DIR%\Scripts\python.exe" -X utf8 scripts\check_release_package.py
if errorlevel 1 goto build_failed

echo تم بناء النسخة بنجاح
echo Build output: dist\AlmiqsAlBaseet
exit /b 0

:build_failed
echo فشل بناء النسخة
exit /b 1

:missing_release_readme
echo RELEASE_README_AR.md غير موجود
goto build_failed
