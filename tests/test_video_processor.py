import pytest

from src.video_processor import (
    AR_EMPTY_LOCAL_VIDEO,
    AR_EMPTY_YOUTUBE_URL,
    AR_UNSUPPORTED_LOCAL_VIDEO,
    INPUT_VIDEO_NAME,
    VideoProcessor,
    VideoSourceError,
    create_project_output_folder,
    validate_local_video_file,
    validate_youtube_url,
)


def test_project_output_folder_sanitizes_project_name(tmp_path) -> None:
    folder = create_project_output_folder("Lesson: 1/2", tmp_path)

    assert folder == tmp_path / "Lesson- 1-2"
    assert folder.is_dir()


@pytest.mark.parametrize("suffix", [".mp4", ".mov", ".mkv", ".webm", ".MP4"])
def test_validate_local_video_file_accepts_common_video_extensions(tmp_path, suffix: str) -> None:
    video_path = tmp_path / f"lesson{suffix}"
    video_path.write_bytes(b"video")

    assert validate_local_video_file(video_path) == video_path


def test_validate_local_video_file_rejects_unsupported_extension(tmp_path) -> None:
    video_path = tmp_path / "lesson.avi"
    video_path.write_bytes(b"video")

    with pytest.raises(VideoSourceError) as error:
        validate_local_video_file(video_path)

    assert str(error.value).startswith(AR_UNSUPPORTED_LOCAL_VIDEO)


@pytest.mark.parametrize("url", [None, "", "   "])
def test_validate_youtube_url_rejects_missing_value(url: str | None) -> None:
    with pytest.raises(VideoSourceError) as error:
        validate_youtube_url(url)

    assert str(error.value) == AR_EMPTY_YOUTUBE_URL


@pytest.mark.parametrize("file_path", [None, "", "   "])
def test_validate_local_video_file_rejects_missing_value(file_path: str | None) -> None:
    with pytest.raises(VideoSourceError) as error:
        validate_local_video_file(file_path)

    assert str(error.value) == AR_EMPTY_LOCAL_VIDEO


def test_prepare_local_video_copies_source_to_project_input(tmp_path) -> None:
    source_path = tmp_path / "source.webm"
    source_path.write_bytes(b"local video")
    processor = VideoProcessor(output_root=tmp_path / "output")

    prepared_video = processor.prepare_local_video(str(source_path), "Project: 1")

    assert prepared_video.project_output_folder.name == "Project- 1"
    assert prepared_video.input_video_path.name == INPUT_VIDEO_NAME
    assert prepared_video.input_video_path.read_bytes() == b"local video"
