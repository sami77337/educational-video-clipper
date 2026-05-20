from src.job_queue import JobStatus, VideoJob, VideoSourceType
from src.job_queue_validation import (
    apply_queue_validation_result,
    format_queue_validation_result_ar,
    validate_queue_job,
)


def test_local_job_validation_with_existing_file(tmp_path) -> None:
    video_path = tmp_path / "lesson.mp4"
    video_path.write_bytes(b"not real video, only existence matters")
    job = VideoJob(source_type=VideoSourceType.LOCAL, source=str(video_path), title="درس")

    result = validate_queue_job(job)

    assert result.status == JobStatus.READY
    assert result.errors == []
    assert "الملف موجود" in result.messages


def test_local_job_validation_with_missing_file(tmp_path) -> None:
    job = VideoJob(source_type="local", source=str(tmp_path / "missing.mp4"), title="درس")

    result = validate_queue_job(job)

    assert result.status == JobStatus.VALIDATION_ERROR
    assert "لم يتم العثور على الملف" in result.errors
    assert "لا يمكن بدء المهمة قبل إصلاح الأخطاء" in format_queue_validation_result_ar(result)


def test_local_job_validation_rejects_non_video_extension(tmp_path) -> None:
    document_path = tmp_path / "lesson.txt"
    document_path.write_text("text", encoding="utf-8")
    job = VideoJob(source_type="local", source=str(document_path), title="درس")

    result = validate_queue_job(job)

    assert result.status == JobStatus.VALIDATION_ERROR
    assert "امتداد الملف لا يبدو كفيديو مدعوم" in result.errors


def test_local_job_validation_warns_about_long_windows_path(tmp_path) -> None:
    long_name = "a" * 245 + ".mp4"
    job = VideoJob(source_type="local", source=str(tmp_path / long_name), title="درس")

    result = validate_queue_job(job)

    assert "المسار طويل وقد يسبب مشكلة في Windows" in result.warnings


def test_youtube_url_detection() -> None:
    job = VideoJob(source_type="youtube", source="https://youtu.be/abc123", title="درس")

    result = validate_queue_job(job)

    assert result.status == JobStatus.READY
    assert result.errors == []
    assert "الرابط صالح مبدئيًا" in result.messages


def test_facebook_url_detection() -> None:
    job = VideoJob(source_type="facebook", source="https://facebook.com/watch/example", title="درس")

    result = validate_queue_job(job)

    assert result.status == JobStatus.READY
    assert result.errors == []
    assert "الرابط صالح مبدئيًا" in result.messages


def test_unsupported_url_handling() -> None:
    job = VideoJob(source_type="youtube", source="https://vimeo.com/123", title="درس")

    result = validate_queue_job(job)

    assert result.status == JobStatus.VALIDATION_ERROR
    assert "رابط يوتيوب غير صالح" in result.errors


def test_invalid_youtube_url_handling() -> None:
    job = VideoJob(source_type="youtube", source="https://youtube.com/watch", title="درس")

    result = validate_queue_job(job)

    assert result.status == JobStatus.VALIDATION_ERROR
    assert "رابط يوتيوب غير صالح" in result.errors


def test_apply_queue_validation_result_updates_job_status_and_messages(tmp_path) -> None:
    video_path = tmp_path / "lesson.mp4"
    video_path.write_bytes(b"ok")
    job = VideoJob(source_type="local", source=str(video_path), title="درس")

    result = validate_queue_job(job)
    apply_queue_validation_result(job, result)

    assert job.status == JobStatus.READY
    assert job.errors == []
    assert job.warnings == []
