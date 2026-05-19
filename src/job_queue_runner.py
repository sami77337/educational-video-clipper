"""Dry-run queue runner skeleton.

This module models future queue execution at the status/summary level only.
It must not download videos, cut clips, call FFmpeg, call yt-dlp, or touch the
current single-video workflow.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from src.job_queue import JobStatus, VideoJob


AR_SIMULATION_ONLY = "تم تشغيل المحاكاة فقط"
AR_NO_DOWNLOADS = "لم يتم تنزيل أي فيديو"
AR_NO_CUTTING = "لم يتم قص أي مقطع"
AR_SKIPPED_WITH_ERRORS = "تم تخطي المهمة بسبب أخطاء"
AR_SIMULATION_FINISHED = "انتهت محاكاة قائمة الانتظار"

ProcessingHook = Callable[[VideoJob], None]


@dataclass(frozen=True)
class JobQueueRunSummary:
    """A dry-run summary for queue execution planning."""

    total_jobs: int
    ready_jobs: int = 0
    skipped_jobs: int = 0
    failed_jobs: int = 0
    completed_simulated_jobs: int = 0
    messages: list[str] = field(default_factory=list)


def run_dry_queue(
    jobs: Iterable[VideoJob],
    *,
    processing_hook: ProcessingHook | None = None,
) -> JobQueueRunSummary:
    """Simulate sequential queue execution without invoking real processing.

    The optional ``processing_hook`` is intentionally never called; it exists
    only so tests and future integration points can prove this skeleton remains
    non-executing until real queue processing is implemented.
    """

    del processing_hook

    job_list = list(jobs)
    ready_jobs = 0
    skipped_jobs = 0
    failed_jobs = 0
    completed_simulated_jobs = 0
    messages = [AR_SIMULATION_ONLY, AR_NO_DOWNLOADS, AR_NO_CUTTING]

    for job in job_list:
        original_status = job.status
        job.status = JobStatus.QUEUED
        job.status = JobStatus.VALIDATING

        if _job_has_blocking_validation_errors(job, original_status):
            job.status = JobStatus.SKIPPED
            skipped_jobs += 1
            messages.append(f"{AR_SKIPPED_WITH_ERRORS}: {job.title}")
            continue

        try:
            job.status = JobStatus.READY
            ready_jobs += 1
            job.status = JobStatus.DONE
            completed_simulated_jobs += 1
        except Exception:
            job.status = JobStatus.FAILED
            failed_jobs += 1

    messages.append(AR_SIMULATION_FINISHED)
    return JobQueueRunSummary(
        total_jobs=len(job_list),
        ready_jobs=ready_jobs,
        skipped_jobs=skipped_jobs,
        failed_jobs=failed_jobs,
        completed_simulated_jobs=completed_simulated_jobs,
        messages=messages,
    )


def simulate_queue_run(
    jobs: Iterable[VideoJob],
    *,
    processing_hook: ProcessingHook | None = None,
) -> JobQueueRunSummary:
    """Alias for callers that prefer explicit simulation wording."""

    return run_dry_queue(jobs, processing_hook=processing_hook)


def format_queue_run_summary_ar(summary: JobQueueRunSummary) -> str:
    """Format dry-run summary lines for UI logs or diagnostics."""

    visible_error_count = summary.failed_jobs + summary.skipped_jobs
    count_lines = [
        f"عدد المهام: {summary.total_jobs}",
        f"المهام الجاهزة: {summary.ready_jobs}",
        f"المهام التي تمت محاكاتها: {summary.completed_simulated_jobs}",
        f"المهام التي تم تخطيها: {summary.skipped_jobs}",
        f"الأخطاء إن وجدت: {visible_error_count}",
    ]
    return "\n".join([*summary.messages, *count_lines])


def _job_has_blocking_validation_errors(job: VideoJob, original_status: JobStatus) -> bool:
    return bool(job.errors) or original_status == JobStatus.VALIDATION_ERROR
