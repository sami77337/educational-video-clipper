import pytest

from src.classification import ClassificationRule
from src.video_processor import (
    AR_EMPTY_LOCAL_VIDEO,
    AR_EMPTY_YOUTUBE_URL,
    AR_UNSUPPORTED_LOCAL_VIDEO,
    BENEFITS_FOLDER_NAME,
    ClipDefinition,
    INPUT_VIDEO_NAME,
    REELS_FOLDER_NAME,
    PreparedVideoSource,
    VideoProcessor,
    VideoSourceError,
    VideoSourceType,
    build_clip_filename,
    build_clip_output_path,
    build_ffmpeg_command,
    calculate_clip_duration,
    classify_clip_folder,
    create_project_output_folder,
    cut_clips,
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


def test_calculate_clip_duration() -> None:
    assert calculate_clip_duration(15, 45) == 30


def test_calculate_clip_duration_rejects_invalid_range() -> None:
    with pytest.raises(ValueError):
        calculate_clip_duration(45, 45)


@pytest.mark.parametrize(
    ("duration", "folder_name"),
    [
        (180, REELS_FOLDER_NAME),
        (181, BENEFITS_FOLDER_NAME),
    ],
)
def test_classify_clip_folder(duration: int, folder_name: str) -> None:
    assert classify_clip_folder(duration) == folder_name


def test_build_clip_filename_sanitizes_arabic_title() -> None:
    clip = ClipDefinition(number=3, title="مقدمة: الدرس/الأول", start_seconds=0, end_seconds=30)

    assert build_clip_filename(clip) == "3_مقدمة- الدرس-الأول.mp4"


def test_build_ffmpeg_command_matches_required_shape(tmp_path) -> None:
    input_path = tmp_path / "input.mp4"
    output_path = tmp_path / REELS_FOLDER_NAME / "1_intro.mp4"

    command = build_ffmpeg_command(input_path, output_path, start_seconds=10, duration_seconds=30)

    assert command == [
        "ffmpeg",
        "-y",
        "-ss",
        "10",
        "-t",
        "30",
        "-i",
        str(input_path),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        str(output_path),
    ]


def test_build_clip_output_path_uses_sorted_folder(tmp_path) -> None:
    clip = ClipDefinition(number=1, title="فائدة", start_seconds=0, end_seconds=181)

    output_path = build_clip_output_path(tmp_path, clip)

    assert output_path == tmp_path / BENEFITS_FOLDER_NAME / "1_فائدة.mp4"
    assert output_path.parent.is_dir()


def test_cut_clips_generates_reels_output_and_logs(tmp_path) -> None:
    input_path = tmp_path / "project" / INPUT_VIDEO_NAME
    input_path.parent.mkdir()
    input_path.write_bytes(b"video")
    prepared_video = PreparedVideoSource(
        source_type=VideoSourceType.LOCAL_FILE,
        project_output_folder=input_path.parent,
        input_video_path=input_path,
    )
    clip = ClipDefinition(number=1, title="ريل قصير", start_seconds=5, end_seconds=25)
    commands: list[list[str]] = []
    messages: list[str] = []

    def fake_runner(command, **kwargs):
        commands.append(command)

    results = cut_clips(prepared_video, [clip], messages.append, fake_runner)

    assert results[0].destination_folder_name == REELS_FOLDER_NAME
    assert results[0].output_path == input_path.parent / REELS_FOLDER_NAME / "1_ريل قصير.mp4"
    assert commands[0][0] == "ffmpeg"
    assert "جاري قص المقطع 1" in messages
    assert "تم الانتهاء من القص والفرز" in messages


def test_cut_clips_uses_custom_classification_folder_and_logs(tmp_path) -> None:
    input_path = tmp_path / "project" / INPUT_VIDEO_NAME
    input_path.parent.mkdir()
    input_path.write_bytes(b"video")
    prepared_video = PreparedVideoSource(
        source_type=VideoSourceType.LOCAL_FILE,
        project_output_folder=input_path.parent,
        input_video_path=input_path,
    )
    clip = ClipDefinition(number=3, title="درس طويل", start_seconds=0, end_seconds=400)
    rules = [
        ClassificationRule("Shorts", 0, 1, "Shorts"),
        ClassificationRule("ريلز", 1, 3, "ريلز"),
        ClassificationRule("دروس", 3, None, "دروس"),
    ]
    messages: list[str] = []

    def fake_runner(command, **kwargs):
        return None

    results = cut_clips(
        prepared_video,
        [clip],
        messages.append,
        fake_runner,
        classification_rules=rules,
    )

    assert results[0].destination_folder_name == "دروس"
    assert results[0].output_path == input_path.parent / "دروس" / "3_درس طويل.mp4"
    assert "تم تصنيف المقطع 03 إلى مجلد دروس" in messages
