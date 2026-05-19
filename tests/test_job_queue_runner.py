from src.job_queue import JobStatus, VideoJob
from src.job_queue_runner import (
    AR_NO_CUTTING,
    AR_NO_DOWNLOADS,
    AR_SIMULATION_FINISHED,
    AR_SIMULATION_ONLY,
    AR_SKIPPED_WITH_ERRORS,
    format_queue_run_summary_ar,
    run_dry_queue,
    simulate_queue_run,
)


def _ready_job(title: str = "درس") -> VideoJob:
    return VideoJob(
        source_type="youtube",
        source="https://youtu.be/example",
        title=title,
        status=JobStatus.READY,
    )


def test_queue_runner_dry_run_with_one_ready_job() -> None:
    job = _ready_job()

    summary = run_dry_queue([job])

    assert job.status == JobStatus.DONE
    assert summary.total_jobs == 1
    assert summary.ready_jobs == 1
    assert summary.completed_simulated_jobs == 1
    assert summary.skipped_jobs == 0
    assert summary.failed_jobs == 0
    assert AR_SIMULATION_ONLY in summary.messages
    assert AR_NO_DOWNLOADS in summary.messages
    assert AR_NO_CUTTING in summary.messages
    assert AR_SIMULATION_FINISHED in summary.messages


def test_queue_runner_processes_multiple_jobs_sequentially() -> None:
    jobs = [_ready_job("الأول"), _ready_job("الثاني"), _ready_job("الثالث")]

    summary = run_dry_queue(jobs)

    assert [job.status for job in jobs] == [JobStatus.DONE, JobStatus.DONE, JobStatus.DONE]
    assert summary.total_jobs == 3
    assert summary.ready_jobs == 3
    assert summary.completed_simulated_jobs == 3
    assert summary.skipped_jobs == 0


def test_queue_runner_skips_validation_error_jobs() -> None:
    invalid_job = VideoJob(
        source_type="youtube",
        source="https://youtu.be/example",
        title="فيه خطأ",
        status=JobStatus.VALIDATION_ERROR,
    )
    ready_job = _ready_job("جاهز")

    summary = run_dry_queue([invalid_job, ready_job])

    assert invalid_job.status == JobStatus.SKIPPED
    assert ready_job.status == JobStatus.DONE
    assert summary.total_jobs == 2
    assert summary.ready_jobs == 1
    assert summary.skipped_jobs == 1
    assert summary.completed_simulated_jobs == 1
    assert any(AR_SKIPPED_WITH_ERRORS in message for message in summary.messages)


def test_queue_runner_skips_jobs_with_errors() -> None:
    job = _ready_job("مشكلة")
    job.errors.append("bad source")

    summary = run_dry_queue([job])

    assert job.status == JobStatus.SKIPPED
    assert summary.skipped_jobs == 1
    assert summary.completed_simulated_jobs == 0


def test_queue_runner_does_not_call_real_processing_hooks() -> None:
    job = _ready_job()

    def forbidden_processing_hook(_job: VideoJob) -> None:
        raise AssertionError("real processing hook should not be called")

    summary = run_dry_queue([job], processing_hook=forbidden_processing_hook)

    assert job.status == JobStatus.DONE
    assert summary.completed_simulated_jobs == 1


def test_queue_runner_summary_counts_and_arabic_formatting() -> None:
    ready_job = _ready_job("جاهز")
    skipped_job = VideoJob(
        source_type="local",
        source="missing.mp4",
        title="مفقود",
        status=JobStatus.VALIDATION_ERROR,
    )

    summary = simulate_queue_run([ready_job, skipped_job])
    formatted = format_queue_run_summary_ar(summary)

    assert summary.total_jobs == 2
    assert summary.ready_jobs == 1
    assert summary.skipped_jobs == 1
    assert summary.failed_jobs == 0
    assert summary.completed_simulated_jobs == 1
    assert "عدد المهام: 2" in formatted
    assert "المهام المتخطاة: 1" in formatted
    assert AR_NO_DOWNLOADS in formatted
    assert AR_NO_CUTTING in formatted


def test_queue_runner_never_starts_real_tools(monkeypatch) -> None:
    def forbidden_import(name: str, *args, **kwargs):
        if name in {"yt_dlp", "subprocess"}:
            raise AssertionError(f"{name} should not be imported by the dry runner")
        return original_import(name, *args, **kwargs)

    original_import = __import__
    monkeypatch.setattr("builtins.__import__", forbidden_import)

    summary = run_dry_queue([_ready_job()])

    assert summary.completed_simulated_jobs == 1
