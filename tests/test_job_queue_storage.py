import json

import pytest

from src.job_queue import ClipJob, JobSettings, JobStatus, VideoJob, VideoSourceType
from src.job_queue_storage import (
    QueueStorageError,
    load_queue_jobs,
    queue_jobs_from_data,
    queue_jobs_to_json,
    save_queue_jobs,
)


def test_serialize_one_video_job() -> None:
    job = VideoJob(
        source_type=VideoSourceType.LOCAL,
        source="C:/videos/lesson.mp4",
        title="درس",
        status=JobStatus.READY,
    )

    data = json.loads(queue_jobs_to_json([job]))

    assert data["schema_version"] == 1
    assert data["jobs"][0]["source_type"] == "local"
    assert data["jobs"][0]["source"] == "C:/videos/lesson.mp4"
    assert data["jobs"][0]["title"] == "درس"
    assert data["jobs"][0]["status"] == "ready"


def test_serialize_video_job_with_saved_clip_rows() -> None:
    job = VideoJob(
        source_type=VideoSourceType.YOUTUBE,
        source="https://youtu.be/abc123",
        title="درس",
        clips=[
            ClipJob(
                title="المقطع الأول",
                start="00:01:00",
                end="00:02:00",
                exclusions="00:01:20-00:01:30",
                notes=["ملاحظة"],
            )
        ],
    )

    loaded = queue_jobs_from_data(json.loads(queue_jobs_to_json([job])))

    assert len(loaded) == 1
    assert loaded[0].source_type == VideoSourceType.YOUTUBE
    assert loaded[0].clips[0].title == "المقطع الأول"
    assert loaded[0].clips[0].start == "00:01:00"
    assert loaded[0].clips[0].end == "00:02:00"
    assert loaded[0].clips[0].exclusions == "00:01:20-00:01:30"
    assert loaded[0].clips[0].notes == ["ملاحظة"]


def test_safe_default_settings_after_load_when_missing() -> None:
    loaded = queue_jobs_from_data(
        {
            "schema_version": 1,
            "jobs": [
                {
                    "source_type": "youtube",
                    "source": "https://youtu.be/abc123",
                    "title": "درس",
                }
            ],
        }
    )

    settings = loaded[0].settings

    assert settings.high_priority is False
    assert settings.speed == 1.0
    assert settings.volume_percent == 100
    assert settings.watermark_enabled is False
    assert settings.silence_reduction_enabled is False


def test_high_priority_is_preserved() -> None:
    job = VideoJob(
        source_type=VideoSourceType.FACEBOOK,
        source="https://facebook.com/watch/example",
        title="درس",
        settings=JobSettings(high_priority=True),
    )

    loaded = queue_jobs_from_data(json.loads(queue_jobs_to_json([job])))

    assert loaded[0].settings.high_priority is True


def test_cookies_and_tokens_are_not_saved() -> None:
    job = VideoJob(
        source_type=VideoSourceType.YOUTUBE,
        source=(
            "https://youtube.com/watch?v=abc123&access_token=secret-token"
            "&cookie=private-cookie&session_id=private-session"
        ),
        title="درس",
        settings=JobSettings(high_priority=True),
    )

    raw_json = queue_jobs_to_json([job])

    assert "secret-token" not in raw_json
    assert "private-cookie" not in raw_json
    assert "private-session" not in raw_json
    assert "access_token" not in raw_json
    assert "cookie" not in raw_json.lower()
    assert "session_id" not in raw_json
    assert "v=abc123" in raw_json


def test_invalid_json_load_handling(tmp_path) -> None:
    file_path = tmp_path / "queue.json"
    file_path.write_text("{not json", encoding="utf-8")

    with pytest.raises(QueueStorageError):
        load_queue_jobs(file_path)


def test_save_and_load_queue_file_roundtrip(tmp_path) -> None:
    file_path = tmp_path / "queue.json"
    job = VideoJob(
        source_type=VideoSourceType.LOCAL,
        source="C:/videos/lesson.mp4",
        title="درس",
        clips=[ClipJob(title="مقطع", start="00:01:00", end="00:02:00")],
        settings=JobSettings(high_priority=True),
    )

    save_queue_jobs([job], file_path)
    loaded = load_queue_jobs(file_path)

    assert loaded[0].title == "درس"
    assert loaded[0].clip_count == 1
    assert loaded[0].settings.high_priority is True
