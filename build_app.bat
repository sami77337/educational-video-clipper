@echo off
setlocal
cd /d "%~dp0"
REM Use the same strict build and package audit as automated Windows builds.
call build_app_ci.bat
if errorlevel 1 (
    echo Build failed. See the error above.
    pause
    exit /b 1
)
echo Send the whole dist\AlmiqsAlBaseet folder, not the EXE alone.
explorer "dist\AlmiqsAlBaseet"
pause
endlocal
