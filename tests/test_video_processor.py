import pytest

from src.classification import ClassificationRule
from src.video_processor import (
    AR_PROJECT_NAME_CLEANED,
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
    build_ffmpeg_concat_command,
    build_ffmpeg_command,
    calculate_clip_duration,
    classify_clip_folder,
    create_project_output_folder,
    cut_clip_with_exclusions,
    cut_clips,
    sanitize_project_name,
    validate_local_video_file,
    validate_youtube_url,
    write_concat_file_list,
)


def test_project_output_folder_sanitizes_project_name(tmp_path) -> None:
    folder = create_project_output_folder("Lesson: 1/2", tmp_path)

    assert folder == tmp_path / "Lesson- 1-2"
    assert folder.is_dir()


def test_sanitize_project_name_supports_arabic_name() -> None:
    assert sanitize_project_name("أسئلة دروس تأسيس ١") == "أسئلة دروس تأسيس ١"


def test_sanitize_project_name_replaces_newlines() -> None:
    project_name = "اسألة دروس تأسيس ١-\n (المجلس الخامس و العشرون)"

    assert sanitize_project_name(project_name) == "اسألة دروس تأسيس ١- (المجلس الخامس و العشرون)"


def test_sanitize_project_name_replaces_tabs() -> None:
    assert sanitize_project_name("درس\tالتفسير\tالأول") == "درس التفسير الأول"


def test_sanitize_project_name_replaces_invalid_windows_characters() -> None:
    assert sanitize_project_name('a\\b/c:d*e?f"g<h>i|j') == "a-b-c-d-e-f-g-h-i-j"


def test_sanitize_project_name_uses_arabic_default_for_empty_name() -> None:
    assert sanitize_project_name(' \n\t <>:"/\\|?* .-') == "مشروع-بدون-اسم"


def test_sanitize_project_name_limits_length() -> None:
    sanitized = sanitize_project_name("أ" * 120)

    assert sanitized == "أ" * 80


def test_project_output_folder_logs_when_project_name_is_cleaned(tmp_path) -> None:
    source_path = tmp_path / "source.mp4"
    source_path.write_bytes(b"video")
    processor = VideoProcessor(output_root=tmp_path / "output")
    messages: list[str] = []

    prepared_video = processor.prepare_local_video(str(source_path), "مشروع\nجديد", messages.append)

    assert AR_PROJECT_NAME_CLEANED in messages
    assert prepared_video.project_output_folder.name == "مشروع جديد"


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
    assert len(commands) == 1
    assert commands[0][0] == "ffmpeg"
    assert "لا توجد استثناءات للمقطع 01" in messages
    assert "تم قص المقطع بدون استثناءات" in messages
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


def test_build_ffmpeg_concat_command_matches_required_shape(tmp_path) -> None:
    file_list = tmp_path / "segments.txt"
    output_path = tmp_path / "final.mp4"

    assert build_ffmpeg_concat_command(file_list, output_path) == [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(file_list),
        "-c",
        "copy",
        str(output_path),
    ]


def test_write_concat_file_list_uses_safe_absolute_paths(tmp_path) -> None:
    first = tmp_path / "segment one.mp4"
    second = tmp_path / "مقطع 2.mp4"

    file_list = write_concat_file_list([first, second], tmp_path / "segments.txt")

    text = file_list.read_text(encoding="utf-8")
    assert "segment one.mp4" in text
    assert "مقطع 2.mp4" in text
    assert "\\\\" not in text


def test_cut_clip_with_one_exclusion_builds_segment_and_concat_commands(tmp_path) -> None:
    input_path = tmp_path / "project" / INPUT_VIDEO_NAME
    input_path.parent.mkdir()
    input_path.write_bytes(b"video")
    output_path = input_path.parent / REELS_FOLDER_NAME / "1_clip.mp4"
    clip = ClipDefinition(
        number=1,
        title="clip",
        start_seconds=1616,
        end_seconds=1754,
        exclusions="00:27:40-00:28:20",
    )
    commands: list[list[str]] = []
    messages: list[str] = []

    def fake_runner(command, **kwargs):
        commands.append(command)

    result = cut_clip_with_exclusions(
        input_path,
        output_path,
        clip,
        input_path.parent / "_temp_segments",
        messages.append,
        fake_runner,
    )

    assert result == output_path
    assert len(commands) == 3
    assert commands[0][commands[0].index("-ss") + 1] == "1616"
    assert commands[0][commands[0].index("-t") + 1] == "44"
    assert commands[1][commands[1].index("-ss") + 1] == "1700"
    assert commands[1][commands[1].index("-t") + 1] == "54"
    assert commands[2][0:6] == ["ffmpeg", "-y", "-f", "concat", "-safe", "0"]
    assert "تم حذف الجزء 00:27:40 - 00:28:20" in messages
    assert "تم دمج أجزاء المقطع 01" in messages
    assert not (input_path.parent / "_temp_segments").exists()


def test_cut_clips_with_multiple_exclusions_uses_all_kept_segments(tmp_path) -> None:
    input_path = tmp_path / "project" / INPUT_VIDEO_NAME
    input_path.parent.mkdir()
    input_path.write_bytes(b"video")
    prepared_video = PreparedVideoSource(
        source_type=VideoSourceType.LOCAL_FILE,
        project_output_folder=input_path.parent,
        input_video_path=input_path,
    )
    clip = ClipDefinition(
        number=2,
        title="multi",
        start_seconds=600,
        end_seconds=900,
        exclusions="00:11:00-00:11:30, 00:13:00-00:13:20",
    )
    commands: list[list[str]] = []

    def fake_runner(command, **kwargs):
        commands.append(command)

    cut_clips(prepared_video, [clip], runner=fake_runner)

    assert len(commands) == 4
    assert [command[command.index("-t") + 1] for command in commands[:3]] == ["60", "90", "100"]
    assert commands[-1][0:6] == ["ffmpeg", "-y", "-f", "concat", "-safe", "0"]


def test_invalid_exclusions_stop_before_ffmpeg(tmp_path) -> None:
    input_path = tmp_path / "project" / INPUT_VIDEO_NAME
    input_path.parent.mkdir()
    input_path.write_bytes(b"video")
    prepared_video = PreparedVideoSource(
        source_type=VideoSourceType.LOCAL_FILE,
        project_output_folder=input_path.parent,
        input_video_path=input_path,
    )
    clip = ClipDefinition(number=1, title="bad", start_seconds=600, end_seconds=900, exclusions="00:09:00-00:09:30")
    commands: list[list[str]] = []

    def fake_runner(command, **kwargs):
        commands.append(command)

    with pytest.raises(Exception) as error:
        cut_clips(prepared_video, [clip], runner=fake_runner)

    assert commands == []
    assert "الاستثناء خارج حدود المقطع" in str(error.value)


def test_dynamic_classification_still_works_with_exclusions(tmp_path) -> None:
    input_path = tmp_path / "project" / INPUT_VIDEO_NAME
    input_path.parent.mkdir()
    input_path.write_bytes(b"video")
    prepared_video = PreparedVideoSource(
        source_type=VideoSourceType.LOCAL_FILE,
        project_output_folder=input_path.parent,
        input_video_path=input_path,
    )
    rules = [ClassificationRule("دروس", 0, None, "دروس")]
    clip = ClipDefinition(
        number=5,
        title="درس",
        start_seconds=0,
        end_seconds=400,
        exclusions="00:01:00-00:01:10",
    )

    def fake_runner(command, **kwargs):
        return None

    results = cut_clips(prepared_video, [clip], runner=fake_runner, classification_rules=rules)

    assert results[0].destination_folder_name == "دروس"
    assert results[0].output_path == input_path.parent / "دروس" / "5_درس.mp4"
