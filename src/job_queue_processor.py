"""Sequential queue processing foundation.

This module owns the state machine for real queue execution.  It keeps the
execution model intentionally simple: one job at a time, no parallel work, and
Facebook jobs left queued until that source is introduced.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from enum import Enum

from src.job_queue import JobStatus, VideoJob, VideoSourceType


AR_QUEUE_JOB_PROCESSING = "جاري معالجة المهمة"
AR_QUEUE_JOB_WAITING = "المهمة في الانتظار"
AR_QUEUE_JOB_DONE = "اكتملت المهمة"
AR_QUEUE_JOB_FAILED = "فشلت المهمة"
AR_QUEUE_JOB_ADDED = "تم إضافة المهمة إلى قائمة الانتظار"
AR_QUEUE_CAN_PREPARE_NEXT = "يمكنك تجهيز مهمة أخرى أثناء المعالجة"
AR_QUEUE_NEXT_JOB_STARTED = "بدأت المهمة التالية"
AR_QUEUE_STOP_AFTER_CURRENT = "سيتم الإيقاف بعد المهمة الحالية"
AR_QUEUE_FINISHED = "انتهت قائمة الانتظار"
AR_URL_QUEUE_PROCESSING_LATER = "تشغيل روابط فيسبوك من قائمة الانتظار سيتم دعمه لاحقًا"
AR_QUEUE_JOB_SKIPPED_ERRORS = "تم تخطي المهمة بسبب أخطاء"
RUNNABLE_QUEUE_SOURCE_TYPES = {VideoSourceType.LOCAL, VideoSourceType.YOUTUBE}


class QueueProcessorState(str, Enum):
    """Lifecycle state for the sequential queue processor."""

    IDLE = "idle"
    RUNNING = "running"
    STOPPING = "stopping"
    FINISHED = "finished"
    FAILED = "failed"


ProcessingHook = Callable[[VideoJob], None]
ProgressCallback = Callable[[str], None]


@dataclass
class QueueProcessingSummary:
    """Counts and messages collected during a queue processing pass."""

    total_jobs: int = 0
    completed_jobs: int = 0
    failed_jobs: int = 0
    skipped_jobs: int = 0
    waiting_jobs: int = 0
    messages: list[str] = field(default_factory=list)


class SequentialQueueProcessor:
    """Run ready local/YouTube queue jobs sequentially through a supplied hook."""

    def __init__(
        self,
        jobs: Iterable[VideoJob],
        *,
        process_job: ProcessingHook,
        progress_callback: ProgressCallback | None = None,
    ) -> None:
        self.jobs = list(jobs)
        self.process_job = process_job
        self.progress_callback = progress_callback
        self.state = QueueProcessorState.IDLE
        self.current_job: VideoJob | None = None
        self.stop_requested = False
        self.summary = QueueProcessingSummary(total_jobs=len(self.jobs))
        self._started_job_count = 0

    @property
    def is_running(self) -> bool:
        return self.state == QueueProcessorState.RUNNING

    def request_stop(self) -> None:
        """Ask the processor to stop after the current job completes."""

        self.stop_requested = True
        if self.state == QueueProcessorState.RUNNING:
            self.state = QueueProcessorState.STOPPING
        self._emit(AR_QUEUE_STOP_AFTER_CURRENT)

    def start_next_job(self) -> VideoJob | None:
        """Mark the next runnable local job as running.

        Calling this while a job is running is a no-op; this is the guard that
        keeps v1 strictly sequential.
        """

        if self.current_job is not None or self.state in {
            QueueProcessorState.RUNNING,
            QueueProcessorState.STOPPING,
        }:
            return None

        job = self._next_runnable_queue_job()
        if job is None:
            self.state = QueueProcessorState.FINISHED
            return None

        job.mark_status(JobStatus.CUTTING)
        self.current_job = job
        self.state = QueueProcessorState.RUNNING
        if self._started_job_count > 0:
            self._emit(AR_QUEUE_NEXT_JOB_STARTED)
            job.add_log(AR_QUEUE_NEXT_JOB_STARTED)
        self._started_job_count += 1
        processing_message = f"{AR_QUEUE_JOB_PROCESSING}: {job.title}"
        job.add_log(processing_message)
        self._emit(processing_message)
        return job

    def complete_current_job(self, *, success: bool, error: str | None = None) -> None:
        """Finish the current job and update queue summary counts."""

        if self.current_job is None:
            return

        job = self.current_job
        if success:
            job.mark_status(JobStatus.DONE)
            self.summary.completed_jobs += 1
            done_message = f"{AR_QUEUE_JOB_DONE}: {job.title}"
            job.add_log(done_message)
            self._emit(done_message)
        else:
            job.mark_status(JobStatus.FAILED)
            if error and not job.failure_message:
                job.mark_failed(error, job.failure_stage or "unknown")
            self.summary.failed_jobs += 1
            failed_message = f"{AR_QUEUE_JOB_FAILED}: {job.title}"
            job.add_log(failed_message)
            self._emit(failed_message)

        self.current_job = None
        self.state = QueueProcessorState.STOPPING if self.stop_requested else QueueProcessorState.IDLE

    def run_until_idle(self) -> QueueProcessingSummary:
        """Process supported jobs one by one until no runnable job remains."""

        self._prepare_non_local_jobs()
        while not self.stop_requested:
            job = self.start_next_job()
            if job is None:
                break

            try:
                self.process_job(job)
            except Exception as exc:
                self.complete_current_job(success=False, error=str(exc))
                self.state = QueueProcessorState.FAILED
                break
            else:
                self.complete_current_job(success=True)

        if self.state != QueueProcessorState.FAILED:
            self.state = QueueProcessorState.FINISHED
        self._emit(AR_QUEUE_FINISHED)
        return self.summary

    def _next_runnable_queue_job(self) -> VideoJob | None:
        for job in self.jobs:
            if job.source_type not in RUNNABLE_QUEUE_SOURCE_TYPES:
                continue
            if job.status in {JobStatus.SKIPPED, JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED}:
                continue
            if job.status == JobStatus.VALIDATION_ERROR or job.has_blocking_errors:
                job.mark_status(JobStatus.SKIPPED)
                self.summary.skipped_jobs += 1
                skipped_message = f"{AR_QUEUE_JOB_SKIPPED_ERRORS}: {job.title}"
                job.add_log(skipped_message)
                self._emit(skipped_message)
                continue
            if job.can_start:
                return job
        return None

    def _prepare_non_local_jobs(self) -> None:
        for job in self.jobs:
            if job.source_type in RUNNABLE_QUEUE_SOURCE_TYPES:
                continue
            if job.status in {JobStatus.READY, JobStatus.WARNING, JobStatus.QUEUED}:
                job.mark_status(JobStatus.QUEUED)
                if AR_URL_QUEUE_PROCESSING_LATER not in job.warnings:
                    job.warnings.append(AR_URL_QUEUE_PROCESSING_LATER)
                self.summary.waiting_jobs += 1
                waiting_message = f"{AR_URL_QUEUE_PROCESSING_LATER}: {job.title}"
                job.add_log(waiting_message)
                self._emit(waiting_message)

    def _emit(self, message: str) -> None:
        self.summary.messages.append(message)
        if self.progress_callback is not None:
            self.progress_callback(message)
