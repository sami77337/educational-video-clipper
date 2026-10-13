"""Nonblocking GitHub release notifications and confirmed one-click updates."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QMessageBox

from src.app_paths import app_directory
from src.github_updates import (
    ReleaseUpdate,
    UpdateError,
    check_latest_release,
    download_verified_update,
    start_installer_after_exit,
)
from src.version import APP_VERSION


class UpdateSignals(QObject):
    succeeded = Signal(object)
    failed = Signal(str)
    progress = Signal(int, int)


class UpdateJob(QRunnable):
    def __init__(self, action: str, release: ReleaseUpdate | None = None) -> None:
        super().__init__()
        self.signals = UpdateSignals()
        self.action = action
        self.release = release

    def run(self) -> None:
        try:
            if self.action == "check":
                result = check_latest_release(APP_VERSION)
            elif self.action == "download" and self.release is not None:
                result = download_verified_update(
                    self.release,
                    progress=lambda received, total: self.signals.progress.emit(received, total),
                )
            else:
                raise UpdateError("عملية التحديث غير معروفة.")
        except Exception as error:
            self.signals.failed.emit(str(error))
        else:
            self.signals.succeeded.emit(result)


class GithubUpdateController(QObject):
    """Leave installation decisions to the user and never interrupt active jobs."""

    def __init__(self, window, button, status_label, *, is_processing):
        super().__init__(window)
        self.window = window
        self.button = button
        self.status_label = status_label
        self.is_processing = is_processing
        self._task: UpdateJob | None = None
        self._silent_check = False
        self._new_release: ReleaseUpdate | None = None
        self._staged_app: Path | None = None
        self._pool = QThreadPool.globalInstance()
        self.button.clicked.connect(self.check_now)
        self.status_label.setText(f"الإصدار المثبت: {APP_VERSION}")

    def check_on_startup(self) -> None:
        # Qt unit tests must remain offline, deterministic and side-effect-free.
        if os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("CI"):
            return
        if getattr(sys, "frozen", False):
            self._start_check(silent=True)

    def check_now(self) -> None:
        if self._task is not None:
            return
        if self._staged_app is not None and self._new_release is not None:
            self._offer_install()
            return
        self._start_check(silent=False)

    def _start_check(self, *, silent: bool) -> None:
        if self._task is not None:
            return
        self._silent_check = silent
        self.status_label.setText("جاري فحص تحديثات GitHub...")
        job = UpdateJob("check")
        job.signals.succeeded.connect(self._check_complete)
        job.signals.failed.connect(self._task_failed)
        self._launch(job)

    def _launch(self, job: UpdateJob) -> None:
        self._task = job
        self.button.setEnabled(False)
        self._pool.start(job)

    def _complete_job(self) -> None:
        self._task = None
        self.button.setEnabled(True)

    def _check_complete(self, release: ReleaseUpdate | None) -> None:
        self._complete_job()
        if release is None:
            self.status_label.setText(f"الإصدار {APP_VERSION} — لا توجد تحديثات جديدة.")
            if not self._silent_check:
                QMessageBox.information(self.window, "تحديثات المقص البسيط", "برنامجك محدث بالفعل.")
            return

        self._new_release = release
        self.status_label.setText(f"تحديث جديد متاح: {release.tag}")
        answer = QMessageBox.question(
            self.window,
            "تحديث جديد للمقص البسيط",
            f"توفّر الإصدار {release.tag} على GitHub.\n"
            "هل ترغب في تنزيله والتحقق من سلامته ثم تثبيته بعد إغلاق البرنامج؟\n"
            "لن يتم تعديل ملفات الفيديو والنتائج.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            self._start_download(release)

    def _start_download(self, release: ReleaseUpdate) -> None:
        if self.is_processing():
            QMessageBox.information(
                self.window, "التحديث مؤجل",
                "هناك قص أو تحميل جارٍ. أكمل معالجة الفيديوهات قبل تثبيت التحديث.",
            )
            return
        self.status_label.setText(f"جاري تنزيل {release.tag} والتحقق من SHA256...")
        job = UpdateJob("download", release)
        job.signals.succeeded.connect(self._download_complete)
        job.signals.failed.connect(self._task_failed)
        job.signals.progress.connect(self._progress)
        self._launch(job)

    def _progress(self, received: int, total: int) -> None:
        received_mb = received / 1024 / 1024
        total_text = f" من {total / 1024 / 1024:.0f}" if total > 0 else ""
        self.status_label.setText(f"تنزيل التحديث: {received_mb:.0f}{total_text} MB")

    def _download_complete(self, stage: Path) -> None:
        self._complete_job()
        self._staged_app = Path(stage)
        self.button.setText("تثبيت التحديث المحمّل")
        self.status_label.setText("اكتمل التنزيل وتحققنا من SHA256. جاهز للتثبيت.")
        self._offer_install()

    def _offer_install(self) -> None:
        if self._staged_app is None:
            return
        if self.is_processing():
            QMessageBox.information(
                self.window, "التحديث مؤجل",
                "أكمل معالجة الفيديوهات أولًا؛ يمكنك تثبيت التحديث من الزر لاحقًا.",
            )
            return
        answer = QMessageBox.question(
            self.window, "تثبيت المقص البسيط",
            "التحديث مُنزَّل وتم التحقق من بصمته.\n"
            "سيُغلق البرنامج ثم يتم استبدال ملفات التشغيل فقط، "
            "مع الاحتفاظ بمجلد النتائج ونسخة احتياطية من الملفات القديمة.\n"
            "هل تريد التثبيت وإعادة تشغيل البرنامج؟",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            start_installer_after_exit(self._staged_app, app_directory())
        except Exception as error:
            QMessageBox.warning(
                self.window, "تعذر التثبيت",
                f"{error}\nيمكنك تنزيل الإصدار يدويًا من GitHub.",
            )
            if self._new_release is not None:
                QDesktopServices.openUrl(QUrl(self._new_release.page_url))
            return
        QApplication.quit()

    def _task_failed(self, message: str) -> None:
        self._complete_job()
        self.status_label.setText("تعذر فحص أو تنزيل التحديث.")
        if not self._silent_check or (self._new_release is not None):
            QMessageBox.warning(
                self.window, "تحديثات GitHub",
                f"{message}\nيمكن الاستمرار باستخدام النسخة الحالية دون تغيير.",
            )
        if self._new_release is not None:
            self.button.setText("فحص تحديثات GitHub")
            self._staged_app = None
