@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

echo بدء التحقق الكامل من الإصدار

set "PYTHON_CMD=python"
where py >nul 2>nul
if not errorlevel 1 set "PYTHON_CMD=py -3"

set "PYTHONIOENCODING=utf-8"
set "QT_QPA_PLATFORM=offscreen"

echo [1/4] تشغيل الاختبارات
%PYTHON_CMD% -X utf8 -m pytest
if errorlevel 1 goto verify_failed

echo [2/4] فحص تشغيل التطبيق
%PYTHON_CMD% -X utf8 -c "from PySide6.QtWidgets import QApplication; from src.main_window import MainWindow; app=QApplication.instance() or QApplication([]); w=MainWindow(); assert w.windowTitle(); w.close(); app.processEvents(); print('app_startup=passed')"
if errorlevel 1 goto verify_failed

echo [3/4] بناء النسخة
call build_app_ci.bat
if errorlevel 1 goto verify_failed

echo [4/4] فحص حزمة الإصدار
%PYTHON_CMD% -X utf8 scripts\check_release_package.py
if errorlevel 1 goto verify_failed

echo تم التحقق الكامل بنجاح
echo Build output: dist\AlmiqsAlBaseet
exit /b 0

:verify_failed
echo فشل التحقق الكامل
exit /b 1
