@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

echo بدء تجهيز المثبت

call verify_release.bat
if errorlevel 1 goto installer_failed

set "ISCC_EXE="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC_EXE=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC_EXE if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC_EXE=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC_EXE (
    for /f "delims=" %%I in ('where ISCC.exe 2^>nul') do (
        if not defined ISCC_EXE set "ISCC_EXE=%%I"
    )
)

if not defined ISCC_EXE (
    echo لم يتم العثور على Inno Setup. تم تجهيز سكربت المثبت فقط.
    echo Installer script: installer\AlmiqsAlBaseet.iss
    exit /b 0
)

if not exist "release\installer" mkdir "release\installer"

"%ISCC_EXE%" "installer\AlmiqsAlBaseet.iss"
if errorlevel 1 goto installer_failed

echo تم بناء المثبت بنجاح
echo Installer output: release\installer
exit /b 0

:installer_failed
echo فشل بناء المثبت
exit /b 1
