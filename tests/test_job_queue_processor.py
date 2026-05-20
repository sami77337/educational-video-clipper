from src.job_queue import ClipJob, JobStatus, VideoJob
from src.job_queue_processor import (
    AR_QUEUE_JOB_DONE,
    AR_QUEUE_JOB_FAILED,
    AR_QUEUE_NEXT_JOB_STARTED,
    AR_URL_QUEUE_PROCESSING_LATER,
    QueueProcessorState,
    SequentialQueueProcessor,
)


def _local_job(title: str = "درس") -> VideoJob:
    return VideoJob(
        source_type="local",
        source="C:/videos/lesson.mp4",
        title=title,
        clips=[ClipJob(title="مقطع", start="00:00:01", end="00:00:05")],
        status=JobStatus.READY,
    )


def _url_job(title: str = "رابط") -> VideoJob:
    return VideoJob(
        source_type="youtube",
        source="https://youtu.be/example",
        title=title,
        clips=[ClipJob(title="مقطع", start="00:00:01", end="00:00:05")],
        status=JobStatus.READY,
    )


def _facebook_job(title: str = "رابط") -> VideoJob:
    return VideoJob(
        source_type="facebook",
        source="https://facebook.com/watch/example",
        title=title,
        clips=[ClipJob(title="مقطع", start="00:00:01", end="00:00:05")],
        status=JobStatus.READY,
    )


def test_queue_processor_state_transitions_for_one_local_job() -> None:
    job = _local_job()
    processed: list[str] = []

    processor = SequentialQueueProcessor([job], process_job=lambda current: processed.append(current.title))
    summary = processor.run_until_idle()

    assert processed == ["درس"]
    assert job.status == JobStatus.DONE
    assert processor.state == QueueProcessorState.FINISHED
    assert summary.completed_jobs == 1
    assert summary.failed_jobs == 0


def test_queue_processor_runs_only_one_job_at_a_time() -> None:
    first = _local_job("الأول")
    second = _local_job("الثاني")
    processor = SequentialQueueProcessor([first, second], process_job=lambda current: None)

    running_job = processor.start_next_job()
    blocked_job = processor.start_next_job()

    assert running_job is first
    assert blocked_job is None
    assert first.status == JobStatus.CUTTING
    assert second.status == JobStatus.READY

    processor.complete_current_job(success=True)
    next_job = processor.start_next_job()

    assert first.status == JobStatus.DONE
    assert next_job is second
    assert second.status == JobStatus.CUTTING


def test_second_job_remains_queued_while_first_is_running() -> None:
    first = _local_job("الأول")
    second = _local_job("الثاني")
    second.status = JobStatus.QUEUED
    processor = SequentialQueueProcessor([first, second], process_job=lambda current: None)

    assert processor.start_next_job() is first

    assert processor.state == QueueProcessorState.RUNNING
    assert second.status == JobStatus.QUEUED


def test_queue_processor_invokes_local_processing_hook_safely() -> None:
    first = _local_job("الأول")
    second = _local_job("الثاني")
    processed: list[str] = []

    summary = SequentialQueueProcessor(
        [first, second],
        process_job=lambda current: processed.append(current.title),
    ).run_until_idle()

    assert processed == ["الأول", "الثاني"]
    assert [first.status, second.status] == [JobStatus.DONE, JobStatus.DONE]
    assert summary.completed_jobs == 2
    assert any(AR_QUEUE_JOB_DONE in message for message in summary.messages)
    assert AR_QUEUE_NEXT_JOB_STARTED in summary.messages


def test_queue_processor_does_not_allow_parallel_start_inside_processing_hook() -> None:
    first = _local_job("الأول")
    second = _local_job("الثاني")
    attempted_parallel_starts: list[VideoJob | None] = []

    def process_current(_job: VideoJob) -> None:
        attempted_parallel_starts.append(processor.start_next_job())

    processor = SequentialQueueProcessor([first, second], process_job=process_current)
    summary = processor.run_until_idle()

    assert attempted_parallel_starts == [None, None]
    assert [first.status, second.status] == [JobStatus.DONE, JobStatus.DONE]
    assert summary.completed_jobs == 2


def test_stop_after_current_prevents_next_job_and_finishes_cleanly() -> None:
    first = _local_job("الأول")
    second = _local_job("الثاني")
    processed: list[str] = []

    def process_current(job: VideoJob) -> None:
        processed.append(job.title)
        processor.request_stop()

    processor = SequentialQueueProcessor([first, second], process_job=process_current)
    summary = processor.run_until_idle()

    assert processed == ["الأول"]
    assert first.status == JobStatus.DONE
    assert second.status == JobStatus.READY
    assert processor.state == QueueProcessorState.FINISHED
    assert processor.stop_requested is True
    assert summary.completed_jobs == 1


def test_youtube_jobs_are_processed_by_queue() -> None:
    job = _url_job()
    processed: list[str] = []

    summary = SequentialQueueProcessor(
        [job],
        process_job=lambda current: processed.append(current.title),
    ).run_until_idle()

    assert processed == ["رابط"]
    assert job.status == JobStatus.DONE
    assert summary.waiting_jobs == 0
    assert summary.completed_jobs == 1


def test_facebook_jobs_are_left_queued_for_later_without_processing() -> None:
    job = _facebook_job()
    processed: list[str] = []

    summary = SequentialQueueProcessor(
        [job],
        process_job=lambda current: processed.append(current.title),
    ).run_until_idle()

    assert processed == []
    assert job.status == JobStatus.QUEUED
    assert AR_URL_QUEUE_PROCESSING_LATER in job.warnings
    assert summary.waiting_jobs == 1
    assert summary.completed_jobs == 0


def test_validation_error_jobs_are_skipped_without_processing() -> None:
    job = _local_job()
    job.status = JobStatus.VALIDATION_ERROR
    processed: list[str] = []

    summary = SequentialQueueProcessor(
        [job],
        process_job=lambda current: processed.append(current.title),
    ).run_until_idle()

    assert processed == []
    assert job.status == JobStatus.SKIPPED
    assert summary.skipped_jobs == 1


def test_failed_local_processing_marks_job_failed() -> None:
    job = _local_job()

    def fail_processing(_job: VideoJob) -> None:
        raise RuntimeError("boom")

    processor = SequentialQueueProcessor([job], process_job=fail_processing)
    summary = processor.run_until_idle()

    assert job.status == JobStatus.FAILED
    assert job.errors == ["boom"]
    assert processor.state == QueueProcessorState.FAILED
    assert summary.failed_jobs == 1
    assert any(AR_QUEUE_JOB_FAILED in message for message in summary.messages)
