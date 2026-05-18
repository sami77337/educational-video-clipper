@echo off
setlocal
cd /d "%~dp0"

REM Creates a desktop shortcut with Arabic display name.
REM If the built EXE exists, the shortcut points to it.
REM Otherwise it points to run_app.bat.

if exist "%~dp0dist\AlmiqsAlBaseet\AlmiqsAlBaseet.exe" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0create_desktop_shortcut.ps1" -TargetPath "%~dp0dist\AlmiqsAlBaseet\AlmiqsAlBaseet.exe" -WorkingDirectory "%~dp0dist\AlmiqsAlBaseet" -IconPath "%~dp0assets\icon.ico"
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0create_desktop_shortcut.ps1" -TargetPath "%~dp0run_app.bat" -WorkingDirectory "%~dp0" -IconPath "%~dp0assets\icon.ico"
)

if errorlevel 1 (
    echo Failed to create desktop shortcut.
    pause
    exit /b 1
)

echo.
echo Desktop shortcut created successfully.
echo You can now open the app from the desktop shortcut.
pause
endlocal
