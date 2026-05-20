import pytest

from src.job_queue import ClipJob, JobSettings, JobStatus, VideoJob, VideoSourceType


def test_video_job_creation() -> None:
    clip = ClipJob(title="مقدمة", start="00:00:10", end="00:00:30")
    job = VideoJob(
        source_type=VideoSourceType.YOUTUBE,
        source="https://youtu.be/example",
        title="درس",
        clips=[clip],
        status=JobStatus.READY,
    )

    assert job.source_type == VideoSourceType.YOUTUBE
    assert job.source == "https://youtu.be/example"
    assert job.title == "درس"
    assert job.clip_count == 1
    assert job.clips[0] == clip


def test_clip_job_creation() -> None:
    clip = ClipJob(
        title="فائدة قصيرة",
        start="00:01:00",
        end="00:02:00",
        exclusions="00:01:20-00:01:30",
        notes=["أول كلمة: بداية"],
        status="ready",
    )

    assert clip.title == "فائدة قصيرة"
    assert clip.start == "00:01:00"
    assert clip.end == "00:02:00"
    assert clip.exclusions == "00:01:20-00:01:30"
    assert clip.notes == ["أول كلمة: بداية"]
    assert clip.status == JobStatus.READY


def test_job_status_values() -> None:
    assert {status.value for status in JobStatus} == {
        "draft",
        "validating",
        "ready",
        "validation_error",
        "warning",
        "queued",
        "downloading",
        "cutting",
        "verifying",
        "done",
        "failed",
        "skipped",
        "cancelled",
    }


def test_default_settings_are_safe() -> None:
    settings = JobSettings()

    assert settings.pre_roll_seconds == 0.0
    assert settings.post_roll_seconds == 0.0
    assert settings.quality_preset == "default"
    assert settings.speed == 1.0
    assert settings.volume_percent == 100
    assert settings.use_browser_login is False
    assert settings.browser_name == "chrome"
    assert settings.watermark_enabled is False
    assert settings.silence_reduction_enabled is False


def test_high_priority_default_is_false() -> None:
    assert JobSettings().high_priority is False


def test_can_start_returns_false_when_job_has_blocking_errors() -> None:
    job = VideoJob(
        source_type="local",
        source="C:/videos/input.mp4",
        title="درس",
        clips=[ClipJob(title="مقطع", start="00:00:01", end="00:00:10")],
        status=JobStatus.READY,
        errors=["missing source"],
    )

    assert job.can_start is False
    assert job.error_count == 1


def test_can_start_returns_false_when_clip_has_blocking_errors() -> None:
    clip = ClipJob(
        title="مقطع",
        start="00:00:01",
        end="00:00:10",
        errors=["invalid time"],
    )
    job = VideoJob(
        source_type="youtube",
        source="https://youtu.be/example",
        title="درس",
        clips=[clip],
        status=JobStatus.READY,
    )

    assert job.can_start is False
    assert job.error_count == 1


def test_can_start_returns_true_for_ready_valid_job() -> None:
    job = VideoJob(
        source_type="facebook",
        source="https://facebook.com/video/example",
        title="درس",
        clips=[ClipJob(title="مقطع", start="00:00:01", end="00:00:10")],
        status="ready",
    )

    assert job.can_start is True


def test_job_counts_warnings_and_errors_across_clips() -> None:
    job = VideoJob(
        source_type="local",
        source="C:/videos/input.mp4",
        title="درس",
        clips=[
            ClipJob(title="الأول", start="00:00:01", end="00:00:10", warnings=["short"]),
            ClipJob(title="الثاني", start="00:00:20", end="00:00:30", errors=["bad"]),
        ],
        warnings=["job warning"],
        errors=["job error"],
    )

    assert job.clip_count == 2
    assert job.warning_count == 2
    assert job.error_count == 2


def test_mark_status_accepts_strings_and_enum_values() -> None:
    job = VideoJob(source_type="local", source="input.mp4", title="درس")
    clip = ClipJob(title="مقطع", start="00:00:01", end="00:00:10")

    job.mark_status("queued")
    clip.mark_status(JobStatus.CUTTING)

    assert job.status == JobStatus.QUEUED
    assert clip.status == JobStatus.CUTTING


def test_invalid_status_is_rejected() -> None:
    with pytest.raises(ValueError):
        ClipJob(title="مقطع", start="00:00:01", end="00:00:10", status="unknown")


def test_invalid_source_type_is_rejected() -> None:
    with pytest.raises(ValueError):
        VideoJob(source_type="vimeo", source="https://example.com", title="درس")
