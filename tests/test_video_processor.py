import subprocess
from pathlib import Path

import pytest

from src.classification import ClassificationRule
from src.clip_padding import ClipPadding
from src.video_speed import AR_INVALID_VIDEO_SPEED
from src.video_volume import AR_INVALID_VOLUME_PERCENT, AR_VOLUME_APPLIED
from src.video_black_flash import AR_BLACK_FLASH_APPLIED, ClipBlackFlash
from src.video_export_quality import AR_EXPORT_QUALITY_APPLIED, ExportQualitySettings
from src.video_fade import AR_FADE_DURATION_CLAMPED, ClipFade
from src.video_processor import (
    AR_BLACK_FADE_APPLIED,
    AR_CLIP_PADDING_APPLIED,
    AR_FFMPEG_NOT_FOUND,
    AR_MULTIPLE_EXCLUSIONS_APPLIED,
    AR_PROJECT_NAME_CLEANED,
    AR_VIDEO_SPEED_APPLIED,
    AR_EMPTY_LOCAL_VIDEO,
    AR_EMPTY_YOUTUBE_URL,
    AR_UNSUPPORTED_LOCAL_VIDEO,
    BENEFITS_FOLDER_NAME,
    ClipDefinition,
    FfmpegNotFoundError,
    INPUT_VIDEO_NAME,
    REELS_FOLDER_NAME,
    PreparedVideoSource,
    VideoProcessor,
    VideoProcessingError,
    VideoSourceRequest,
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
    cut_clip,
    download_youtube_video,
    verify_output_duration,
)


YOUTUBE_BEST_VIDEO_AUDIO_FORMAT = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"


def _capture_youtube_options(tmp_path, **download_kwargs) -> dict:
    destination = tmp_path / "input.mp4"
    captured_options: dict = {}

    class FakeYoutubeDL:
        def __init__(self, options):
            captured_options.update(options)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def download(self, urls):
            Path(captured_options["outtmpl"]).write_bytes(b"video")

    download_youtube_video("https://youtu.be/example", destination, FakeYoutubeDL, **download_kwargs)
    return captured_options


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
    assert commands[0][commands[0].index("-ss") + 1] == "5"
    assert commands[0][commands[0].index("-t") + 1] == "20"
    assert AR_CLIP_PADDING_APPLIED not in messages
    assert "لا توجد استثناءات للمقطع 01" in messages
    assert "تم قص المقطع بدون استثناءات" in messages
    assert "جاري قص المقطع 1" in messages
    assert "تم الانتهاء من القص والفرز" in messages


def test_cut_clips_applies_pre_and_post_padding_to_ffmpeg_command(tmp_path) -> None:
    input_path = tmp_path / "project" / INPUT_VIDEO_NAME
    input_path.parent.mkdir()
    input_path.write_bytes(b"video")
    prepared_video = PreparedVideoSource(
        source_type=VideoSourceType.LOCAL_FILE,
        project_output_folder=input_path.parent,
        input_video_path=input_path,
    )
    clip = ClipDefinition(number=1, title="clip", start_seconds=5, end_seconds=25)
    commands: list[list[str]] = []
    messages: list[str] = []

    def fake_runner(command, **kwargs):
        commands.append(command)

    cut_clips(
        prepared_video,
        [clip],
        messages.append,
        fake_runner,
        clip_padding=ClipPadding(pre_seconds=0.5, post_seconds=1),
    )

    assert commands[0][commands[0].index("-ss") + 1] == "4.5"
    assert commands[0][commands[0].index("-t") + 1] == "21.5"
    assert AR_CLIP_PADDING_APPLIED in messages


def test_cut_clips_speed_one_preserves_existing_ffmpeg_command(tmp_path) -> None:
    input_path = tmp_path / "project" / INPUT_VIDEO_NAME
    input_path.parent.mkdir()
    input_path.write_bytes(b"video")
    prepared_video = PreparedVideoSource(
        source_type=VideoSourceType.LOCAL_FILE,
        project_output_folder=input_path.parent,
        input_video_path=input_path,
    )
    clip = ClipDefinition(number=1, title="clip", start_seconds=5, end_seconds=25)
    commands: list[list[str]] = []

    def fake_runner(command, **kwargs):
        commands.append(command)

    cut_clips(prepared_video, [clip], runner=fake_runner, video_speed=1.0)

    assert "-filter:v" not in commands[0]
    assert "-filter:a" not in commands[0]
    assert commands[0][commands[0].index("-ss") + 1] == "5"
    assert commands[0][commands[0].index("-t") + 1] == "20"


def test_cut_clips_disabled_fade_preserves_existing_ffmpeg_command(tmp_path) -> None:
    input_path = tmp_path / "project" / INPUT_VIDEO_NAME
    input_path.parent.mkdir()
    input_path.write_bytes(b"video")
    prepared_video = PreparedVideoSource(
        source_type=VideoSourceType.LOCAL_FILE,
        project_output_folder=input_path.parent,
        input_video_path=input_path,
    )
    clip = ClipDefinition(number=1, title="clip", start_seconds=5, end_seconds=25)
    default_commands: list[list[str]] = []
    fade_disabled_commands: list[list[str]] = []

    cut_clips(prepared_video, [clip], runner=lambda command, **kwargs: default_commands.append(command))
    cut_clips(
        prepared_video,
        [clip],
        runner=lambda command, **kwargs: fade_disabled_commands.append(command),
        clip_fade=ClipFade(enabled=False, fade_in_seconds=2.0, fade_out_seconds=2.0),
    )

    assert fade_disabled_commands == default_commands
    assert "-filter:v" not in fade_disabled_commands[0]


def test_cut_clips_disabled_export_quality_preserves_existing_ffmpeg_command(tmp_path) -> None:
    input_path = tmp_path / "project" / INPUT_VIDEO_NAME
    input_path.parent.mkdir()
    input_path.write_bytes(b"video")
    prepared_video = PreparedVideoSource(
        source_type=VideoSourceType.LOCAL_FILE,
        project_output_folder=input_path.parent,
        input_video_path=input_path,
    )
    clip = ClipDefinition(number=1, title="clip", start_seconds=5, end_seconds=25)
    default_commands: list[list[str]] = []
    disabled_quality_commands: list[list[str]] = []

    cut_clips(prepared_video, [clip], runner=lambda command, **kwargs: default_commands.append(command))
    cut_clips(
        prepared_video,
        [clip],
        runner=lambda command, **kwargs: disabled_quality_commands.append(command),
        export_quality=ExportQualitySettings(enabled=False, quality_preset="small", resolution_limit="720p"),
    )

    assert disabled_quality_commands == default_commands


def test_cut_clips_applies_custom_export_quality_and_resolution(tmp_path) -> None:
    input_path = tmp_path / "project" / INPUT_VIDEO_NAME
    input_path.parent.mkdir()
    input_path.write_bytes(b"video")
    prepared_video = PreparedVideoSource(
        source_type=VideoSourceType.LOCAL_FILE,
        project_output_folder=input_path.parent,
        input_video_path=input_path,
    )
    clip = ClipDefinition(number=1, title="clip", start_seconds=5, end_seconds=25)
    commands: list[list[str]] = []
    messages: list[str] = []

    cut_clips(
        prepared_video,
        [clip],
        messages.append,
        lambda command, **kwargs: commands.append(command),
        export_quality=ExportQualitySettings(enabled=True, quality_preset="high", resolution_limit="1080p"),
    )

    assert commands[0][commands[0].index("-preset") + 1] == "slow"
    assert commands[0][commands[0].index("-crf") + 1] == "18"
    assert "scale=" in commands[0][commands[0].index("-filter:v") + 1]
    assert AR_EXPORT_QUALITY_APPLIED in messages


@pytest.mark.parametrize(
    ("speed", "formatted_speed"),
    [
        (1.05, "1.05"),
        (1.10, "1.1"),
        (1.25, "1.25"),
    ],
)
def test_cut_clips_applies_synced_video_speed_to_ffmpeg_command(
    tmp_path,
    speed: float,
    formatted_speed: str,
) -> None:
    input_path = tmp_path / "project" / INPUT_VIDEO_NAME
    input_path.parent.mkdir()
    input_path.write_bytes(b"video")
    prepared_video = PreparedVideoSource(
        source_type=VideoSourceType.LOCAL_FILE,
        project_output_folder=input_path.parent,
        input_video_path=input_path,
    )
    clip = ClipDefinition(number=1, title="clip", start_seconds=5, end_seconds=25)
    commands: list[list[str]] = []
    messages: list[str] = []

    def fake_runner(command, **kwargs):
        commands.append(command)

    cut_clips(prepared_video, [clip], messages.append, fake_runner, video_speed=speed)

    assert commands[0][commands[0].index("-filter:v") + 1] == f"setpts=PTS/{formatted_speed}"
    assert commands[0][commands[0].index("-filter:a") + 1] == f"atempo={formatted_speed}"
    assert AR_VIDEO_SPEED_APPLIED in messages


@pytest.mark.parametrize(
    ("volume_percent", "audio_filter"),
    [
        (75, "volume=0.75"),
        (150, "volume=1.5"),
        (200, "volume=2"),
    ],
)
def test_cut_clips_applies_audio_volume_to_ffmpeg_command(
    tmp_path,
    volume_percent: int,
    audio_filter: str,
) -> None:
    input_path = tmp_path / "project" / INPUT_VIDEO_NAME
    input_path.parent.mkdir()
    input_path.write_bytes(b"video")
    prepared_video = PreparedVideoSource(
        source_type=VideoSourceType.LOCAL_FILE,
        project_output_folder=input_path.parent,
        input_video_path=input_path,
    )
    clip = ClipDefinition(number=1, title="clip", start_seconds=5, end_seconds=25)
    commands: list[list[str]] = []
    messages: list[str] = []

    def fake_runner(command, **kwargs):
        commands.append(command)

    cut_clips(prepared_video, [clip], messages.append, fake_runner, volume_percent=volume_percent)

    assert "-filter:v" not in commands[0]
    assert commands[0][commands[0].index("-filter:a") + 1] == audio_filter
    assert AR_VOLUME_APPLIED in messages


def test_cut_clips_applies_speed_and_volume_together(tmp_path) -> None:
    input_path = tmp_path / "project" / INPUT_VIDEO_NAME
    input_path.parent.mkdir()
    input_path.write_bytes(b"video")
    prepared_video = PreparedVideoSource(
        source_type=VideoSourceType.LOCAL_FILE,
        project_output_folder=input_path.parent,
        input_video_path=input_path,
    )
    clip = ClipDefinition(number=1, title="clip", start_seconds=5, end_seconds=25)
    commands: list[list[str]] = []
    messages: list[str] = []

    def fake_runner(command, **kwargs):
        commands.append(command)

    cut_clips(
        prepared_video,
        [clip],
        messages.append,
        fake_runner,
        video_speed=1.10,
        volume_percent=150,
    )

    assert commands[0][commands[0].index("-filter:v") + 1] == "setpts=PTS/1.1"
    assert commands[0][commands[0].index("-filter:a") + 1] == "atempo=1.1,volume=1.5"
    assert AR_VIDEO_SPEED_APPLIED in messages
    assert AR_VOLUME_APPLIED in messages


def test_cut_clips_applies_black_fade_to_ffmpeg_command(tmp_path) -> None:
    input_path = tmp_path / "project" / INPUT_VIDEO_NAME
    input_path.parent.mkdir()
    input_path.write_bytes(b"video")
    prepared_video = PreparedVideoSource(
        source_type=VideoSourceType.LOCAL_FILE,
        project_output_folder=input_path.parent,
        input_video_path=input_path,
    )
    clip = ClipDefinition(number=1, title="clip", start_seconds=5, end_seconds=25)
    commands: list[list[str]] = []
    messages: list[str] = []

    cut_clips(
        prepared_video,
        [clip],
        messages.append,
        lambda command, **kwargs: commands.append(command),
        clip_fade=ClipFade(enabled=True, fade_in_seconds=0.5, fade_out_seconds=0.5),
    )

    assert commands[0][commands[0].index("-filter:v") + 1] == (
        "fade=t=in:st=0:d=0.5,fade=t=out:st=19.5:d=0.5"
    )
    assert "-filter:a" not in commands[0]
    assert AR_BLACK_FADE_APPLIED in messages


def test_cut_clips_clamps_black_fade_for_short_clip(tmp_path) -> None:
    input_path = tmp_path / "project" / INPUT_VIDEO_NAME
    input_path.parent.mkdir()
    input_path.write_bytes(b"video")
    prepared_video = PreparedVideoSource(
        source_type=VideoSourceType.LOCAL_FILE,
        project_output_folder=input_path.parent,
        input_video_path=input_path,
    )
    clip = ClipDefinition(number=1, title="clip", start_seconds=5, end_seconds=6)
    commands: list[list[str]] = []
    messages: list[str] = []

    cut_clips(
        prepared_video,
        [clip],
        messages.append,
        lambda command, **kwargs: commands.append(command),
        clip_fade=ClipFade(enabled=True, fade_in_seconds=1.0, fade_out_seconds=1.0),
    )

    assert commands[0][commands[0].index("-filter:v") + 1] == (
        "fade=t=in:st=0:d=0.5,fade=t=out:st=0.5:d=0.5"
    )
    assert AR_FADE_DURATION_CLAMPED in messages


def test_cut_clips_composes_fade_with_speed_volume_padding_and_exclusions(tmp_path) -> None:
    input_path = tmp_path / "project" / INPUT_VIDEO_NAME
    input_path.parent.mkdir()
    input_path.write_bytes(b"video")
    prepared_video = PreparedVideoSource(
        source_type=VideoSourceType.LOCAL_FILE,
        project_output_folder=input_path.parent,
        input_video_path=input_path,
    )
    clip = ClipDefinition(
        number=1,
        title="clip",
        start_seconds=10,
        end_seconds=20,
        exclusions="00:00:14-00:00:15",
    )
    commands: list[list[str]] = []
    messages: list[str] = []

    cut_clips(
        prepared_video,
        [clip],
        messages.append,
        lambda command, **kwargs: commands.append(command),
        clip_padding=ClipPadding(pre_seconds=1, post_seconds=1),
        video_speed=1.25,
        volume_percent=150,
        clip_fade=ClipFade(enabled=True, fade_in_seconds=0.5, fade_out_seconds=0.5),
    )

    segment_commands = [command for command in commands if "segment_" in str(command[-1])]
    final_fade_command = commands[-1]
    assert len(segment_commands) == 2
    assert segment_commands[0][segment_commands[0].index("-filter:v") + 1] == "setpts=PTS/1.25"
    assert segment_commands[0][segment_commands[0].index("-filter:a") + 1] == "atempo=1.25,volume=1.5"
    assert final_fade_command[final_fade_command.index("-filter:v") + 1].startswith("fade=t=in")
    assert "-filter:a" not in final_fade_command
    assert final_fade_command[final_fade_command.index("-c:a") + 1] == "copy"
    assert AR_CLIP_PADDING_APPLIED in messages
    assert AR_VIDEO_SPEED_APPLIED in messages
    assert AR_VOLUME_APPLIED in messages
    assert AR_BLACK_FADE_APPLIED in messages


def test_process_project_rejects_invalid_video_speed_before_preparing_source(tmp_path, monkeypatch) -> None:
    processor = VideoProcessor(output_root=tmp_path)
    prepared: list[bool] = []
    monkeypatch.setattr(processor, "prepare_source", lambda *args, **kwargs: prepared.append(True))

    with pytest.raises(VideoProcessingError) as error:
        processor.process_project(
            VideoSourceRequest(VideoSourceType.LOCAL_FILE, "C:/videos/lesson.mp4"),
            "Project",
            [],
            video_speed=0,
        )

    assert str(error.value) == AR_INVALID_VIDEO_SPEED
    assert prepared == []


def test_process_project_rejects_invalid_volume_before_preparing_source(tmp_path, monkeypatch) -> None:
    processor = VideoProcessor(output_root=tmp_path)
    prepared: list[bool] = []
    monkeypatch.setattr(processor, "prepare_source", lambda *args, **kwargs: prepared.append(True))

    with pytest.raises(VideoProcessingError) as error:
        processor.process_project(
            VideoSourceRequest(VideoSourceType.LOCAL_FILE, "C:/videos/lesson.mp4"),
            "Project",
            [],
            volume_percent=0,
        )

    assert str(error.value) == AR_INVALID_VOLUME_PERCENT
    assert prepared == []


def test_cut_clips_clamps_post_padding_to_known_video_duration(tmp_path) -> None:
    input_path = tmp_path / "project" / INPUT_VIDEO_NAME
    input_path.parent.mkdir()
    input_path.write_bytes(b"video")
    prepared_video = PreparedVideoSource(
        source_type=VideoSourceType.LOCAL_FILE,
        project_output_folder=input_path.parent,
        input_video_path=input_path,
    )
    clip = ClipDefinition(number=1, title="clip", start_seconds=10, end_seconds=20)
    commands: list[list[str]] = []

    def fake_runner(command, **kwargs):
        commands.append(command)

    cut_clips(
        prepared_video,
        [clip],
        runner=fake_runner,
        clip_padding=ClipPadding(post_seconds=10),
        video_duration_seconds=25,
    )

    assert commands[0][commands[0].index("-ss") + 1] == "10"
    assert commands[0][commands[0].index("-t") + 1] == "15"


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


def test_cut_clip_with_exclusion_applies_speed_to_segments(tmp_path) -> None:
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

    def fake_runner(command, **kwargs):
        commands.append(command)

    cut_clip_with_exclusions(
        input_path,
        output_path,
        clip,
        input_path.parent / "_temp_segments",
        runner=fake_runner,
        video_speed=1.05,
    )

    assert commands[0][commands[0].index("-filter:v") + 1] == "setpts=PTS/1.05"
    assert commands[0][commands[0].index("-filter:a") + 1] == "atempo=1.05"
    assert commands[1][commands[1].index("-filter:v") + 1] == "setpts=PTS/1.05"
    assert commands[1][commands[1].index("-filter:a") + 1] == "atempo=1.05"
    assert commands[2][0:6] == ["ffmpeg", "-y", "-f", "concat", "-safe", "0"]


def test_cut_clip_with_exclusion_uses_effective_padded_bounds(tmp_path) -> None:
    input_path = tmp_path / "project" / INPUT_VIDEO_NAME
    input_path.parent.mkdir()
    input_path.write_bytes(b"video")
    output_path = input_path.parent / REELS_FOLDER_NAME / "1_clip.mp4"
    clip = ClipDefinition(
        number=1,
        title="clip",
        start_seconds=100,
        end_seconds=200,
        exclusions="00:02:30-00:02:40",
    )
    commands: list[list[str]] = []

    def fake_runner(command, **kwargs):
        commands.append(command)

    cut_clip_with_exclusions(
        input_path,
        output_path,
        clip,
        input_path.parent / "_temp_segments",
        runner=fake_runner,
        effective_start_seconds=95,
        effective_end_seconds=202,
    )

    assert commands[0][commands[0].index("-ss") + 1] == "95"
    assert commands[0][commands[0].index("-t") + 1] == "55"
    assert commands[1][commands[1].index("-ss") + 1] == "160"
    assert commands[1][commands[1].index("-t") + 1] == "42"


def test_disabled_black_flash_preserves_old_exclusion_command_behavior(tmp_path) -> None:
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
    default_commands: list[list[str]] = []
    flash_disabled_commands: list[list[str]] = []

    cut_clip_with_exclusions(
        input_path,
        output_path,
        clip,
        input_path.parent / "_temp_segments",
        runner=lambda command, **kwargs: default_commands.append(command),
    )
    cut_clip_with_exclusions(
        input_path,
        output_path,
        clip,
        input_path.parent / "_temp_segments",
        runner=lambda command, **kwargs: flash_disabled_commands.append(command),
        clip_black_flash=ClipBlackFlash(enabled=False, duration_seconds=0.5),
    )

    assert flash_disabled_commands == default_commands
    assert all("drawbox" not in " ".join(command) for command in flash_disabled_commands)


def test_enabled_black_flash_applies_video_marker_at_single_exclusion_join(tmp_path) -> None:
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

    cut_clip_with_exclusions(
        input_path,
        output_path,
        clip,
        input_path.parent / "_temp_segments",
        messages.append,
        lambda command, **kwargs: commands.append(command),
        clip_black_flash=ClipBlackFlash(enabled=True, duration_seconds=0.2),
    )

    assert len(commands) == 4
    final_effect_command = commands[-1]
    video_filter = final_effect_command[final_effect_command.index("-filter:v") + 1]
    assert "drawbox" in video_filter
    assert "between(t,44,44.2)" in video_filter
    assert final_effect_command[final_effect_command.index("-c:a") + 1] == "copy"
    assert AR_BLACK_FLASH_APPLIED in messages


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
    messages: list[str] = []

    def fake_runner(command, **kwargs):
        commands.append(command)

    cut_clips(prepared_video, [clip], messages.append, fake_runner)

    assert len(commands) == 4
    assert [command[command.index("-t") + 1] for command in commands[:3]] == ["60", "90", "100"]
    assert commands[-1][0:6] == ["ffmpeg", "-y", "-f", "concat", "-safe", "0"]
    assert f"{AR_MULTIPLE_EXCLUSIONS_APPLIED} 02" in messages


def test_enabled_black_flash_applies_video_markers_at_multiple_exclusion_joins(tmp_path) -> None:
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
    messages: list[str] = []

    cut_clips(
        prepared_video,
        [clip],
        messages.append,
        lambda command, **kwargs: commands.append(command),
        clip_black_flash=ClipBlackFlash(enabled=True, duration_seconds=0.3),
    )

    assert len(commands) == 5
    final_effect_command = commands[-1]
    video_filter = final_effect_command[final_effect_command.index("-filter:v") + 1]
    assert "between(t,60,60.3)" in video_filter
    assert "between(t,150,150.3)" in video_filter
    assert AR_BLACK_FLASH_APPLIED in messages


def test_export_quality_composes_with_speed_volume_fade_flash_padding_and_exclusions(tmp_path) -> None:
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
    messages: list[str] = []

    cut_clips(
        prepared_video,
        [clip],
        messages.append,
        lambda command, **kwargs: commands.append(command),
        clip_padding=ClipPadding(pre_seconds=1, post_seconds=1),
        video_speed=1.10,
        volume_percent=150,
        clip_fade=ClipFade(enabled=True, fade_in_seconds=0.5, fade_out_seconds=0.5),
        clip_black_flash=ClipBlackFlash(enabled=True, duration_seconds=0.2),
        export_quality=ExportQualitySettings(enabled=True, quality_preset="small", resolution_limit="720p"),
    )

    segment_command = commands[0]
    final_effect_command = commands[-1]
    assert segment_command[segment_command.index("-preset") + 1] == "veryfast"
    assert segment_command[segment_command.index("-crf") + 1] == "26"
    assert "setpts=PTS/1.1" in segment_command[segment_command.index("-filter:v") + 1]
    assert "scale=" in segment_command[segment_command.index("-filter:v") + 1]
    assert segment_command[segment_command.index("-filter:a") + 1] == "atempo=1.1,volume=1.5"
    assert "drawbox" in final_effect_command[final_effect_command.index("-filter:v") + 1]
    assert "fade=t=in" in final_effect_command[final_effect_command.index("-filter:v") + 1]
    assert "scale=" in final_effect_command[final_effect_command.index("-filter:v") + 1]
    assert final_effect_command[final_effect_command.index("-crf") + 1] == "26"
    assert AR_CLIP_PADDING_APPLIED in messages
    assert AR_VIDEO_SPEED_APPLIED in messages
    assert AR_VOLUME_APPLIED in messages
    assert AR_BLACK_FADE_APPLIED in messages
    assert AR_BLACK_FLASH_APPLIED in messages
    assert AR_EXPORT_QUALITY_APPLIED in messages


def test_black_flash_enabled_does_nothing_for_clip_without_exclusions(tmp_path) -> None:
    input_path = tmp_path / "project" / INPUT_VIDEO_NAME
    input_path.parent.mkdir()
    input_path.write_bytes(b"video")
    prepared_video = PreparedVideoSource(
        source_type=VideoSourceType.LOCAL_FILE,
        project_output_folder=input_path.parent,
        input_video_path=input_path,
    )
    clip = ClipDefinition(number=1, title="clip", start_seconds=5, end_seconds=25)
    commands: list[list[str]] = []
    messages: list[str] = []

    cut_clips(
        prepared_video,
        [clip],
        messages.append,
        lambda command, **kwargs: commands.append(command),
        clip_black_flash=ClipBlackFlash(enabled=True, duration_seconds=0.2),
    )

    assert len(commands) == 1
    assert "-filter:v" not in commands[0]
    assert AR_BLACK_FLASH_APPLIED not in messages


def test_cut_clips_accepts_semicolon_separated_multiple_exclusions(tmp_path) -> None:
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
        exclusions="00:11:00-00:11:30; 00:13:00-00:13:20",
    )
    commands: list[list[str]] = []

    def fake_runner(command, **kwargs):
        commands.append(command)

    cut_clips(prepared_video, [clip], runner=fake_runner)

    assert len(commands) == 4
    assert [command[command.index("-t") + 1] for command in commands[:3]] == ["60", "90", "100"]


def test_cut_clips_sorts_multiple_exclusions_before_cutting(tmp_path) -> None:
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
        exclusions="00:13:00-00:13:20, 00:11:00-00:11:30",
    )
    commands: list[list[str]] = []

    def fake_runner(command, **kwargs):
        commands.append(command)

    cut_clips(prepared_video, [clip], runner=fake_runner)

    assert len(commands) == 4
    assert [command[command.index("-ss") + 1] for command in commands[:3]] == ["600", "690", "800"]
    assert [command[command.index("-t") + 1] for command in commands[:3]] == ["60", "90", "100"]


def test_cut_clips_applies_multiple_exclusions_with_padding(tmp_path) -> None:
    input_path = tmp_path / "project" / INPUT_VIDEO_NAME
    input_path.parent.mkdir()
    input_path.write_bytes(b"video")
    prepared_video = PreparedVideoSource(
        source_type=VideoSourceType.LOCAL_FILE,
        project_output_folder=input_path.parent,
        input_video_path=input_path,
    )
    clip = ClipDefinition(
        number=3,
        title="padded multi",
        start_seconds=100,
        end_seconds=200,
        exclusions="00:02:00-00:02:10, 00:02:40-00:02:45",
    )
    commands: list[list[str]] = []

    def fake_runner(command, **kwargs):
        commands.append(command)

    cut_clips(
        prepared_video,
        [clip],
        runner=fake_runner,
        clip_padding=ClipPadding(pre_seconds=10, post_seconds=5),
    )

    assert len(commands) == 4
    assert [command[command.index("-ss") + 1] for command in commands[:3]] == ["90", "130", "165"]
    assert [command[command.index("-t") + 1] for command in commands[:3]] == ["30", "30", "40"]


def test_cut_clips_speed_and_volume_preserve_padding_and_multiple_exclusion_commands(tmp_path) -> None:
    input_path = tmp_path / "project" / INPUT_VIDEO_NAME
    input_path.parent.mkdir()
    input_path.write_bytes(b"video")
    prepared_video = PreparedVideoSource(
        source_type=VideoSourceType.LOCAL_FILE,
        project_output_folder=input_path.parent,
        input_video_path=input_path,
    )
    clip = ClipDefinition(
        number=3,
        title="padded multi speed",
        start_seconds=100,
        end_seconds=200,
        exclusions="00:02:00-00:02:10, 00:02:40-00:02:45",
    )
    commands: list[list[str]] = []
    messages: list[str] = []

    def fake_runner(command, **kwargs):
        commands.append(command)

    cut_clips(
        prepared_video,
        [clip],
        messages.append,
        fake_runner,
        clip_padding=ClipPadding(pre_seconds=10, post_seconds=5),
        video_speed=1.25,
        volume_percent=150,
    )

    assert len(commands) == 4
    assert [command[command.index("-ss") + 1] for command in commands[:3]] == ["90", "130", "165"]
    assert [command[command.index("-t") + 1] for command in commands[:3]] == ["30", "30", "40"]
    for command in commands[:3]:
        assert command[command.index("-filter:v") + 1] == "setpts=PTS/1.25"
        assert command[command.index("-filter:a") + 1] == "atempo=1.25,volume=1.5"
    assert commands[-1][0:6] == ["ffmpeg", "-y", "-f", "concat", "-safe", "0"]
    assert AR_CLIP_PADDING_APPLIED in messages
    assert f"{AR_MULTIPLE_EXCLUSIONS_APPLIED} 03" in messages
    assert AR_VIDEO_SPEED_APPLIED in messages
    assert AR_VOLUME_APPLIED in messages


def test_black_flash_composes_with_speed_volume_fade_and_padding(tmp_path) -> None:
    input_path = tmp_path / "project" / INPUT_VIDEO_NAME
    input_path.parent.mkdir()
    input_path.write_bytes(b"video")
    prepared_video = PreparedVideoSource(
        source_type=VideoSourceType.LOCAL_FILE,
        project_output_folder=input_path.parent,
        input_video_path=input_path,
    )
    clip = ClipDefinition(
        number=3,
        title="padded multi speed",
        start_seconds=100,
        end_seconds=200,
        exclusions="00:02:00-00:02:10, 00:02:40-00:02:45",
    )
    commands: list[list[str]] = []
    messages: list[str] = []

    cut_clips(
        prepared_video,
        [clip],
        messages.append,
        lambda command, **kwargs: commands.append(command),
        clip_padding=ClipPadding(pre_seconds=10, post_seconds=5),
        video_speed=1.25,
        volume_percent=150,
        clip_fade=ClipFade(enabled=True, fade_in_seconds=0.5, fade_out_seconds=0.5),
        clip_black_flash=ClipBlackFlash(enabled=True, duration_seconds=0.2),
    )

    final_effect_command = commands[-1]
    video_filter = final_effect_command[final_effect_command.index("-filter:v") + 1]
    assert "drawbox" in video_filter
    assert "between(t,24,24.2)" in video_filter
    assert "between(t,48,48.2)" in video_filter
    assert "fade=t=in:st=0:d=0.5" in video_filter
    assert final_effect_command[final_effect_command.index("-c:a") + 1] == "copy"
    for command in commands[:3]:
        assert command[command.index("-filter:v") + 1] == "setpts=PTS/1.25"
        assert command[command.index("-filter:a") + 1] == "atempo=1.25,volume=1.5"
    assert AR_BLACK_FLASH_APPLIED in messages
    assert AR_BLACK_FADE_APPLIED in messages


def test_cut_clips_validates_exclusions_against_effective_padded_range(tmp_path) -> None:
    input_path = tmp_path / "project" / INPUT_VIDEO_NAME
    input_path.parent.mkdir()
    input_path.write_bytes(b"video")
    prepared_video = PreparedVideoSource(
        source_type=VideoSourceType.LOCAL_FILE,
        project_output_folder=input_path.parent,
        input_video_path=input_path,
    )
    clip = ClipDefinition(
        number=3,
        title="padded edge exclusions",
        start_seconds=100,
        end_seconds=200,
        exclusions="00:01:35-00:01:38, 00:03:25-00:03:28",
    )
    commands: list[list[str]] = []

    def fake_runner(command, **kwargs):
        commands.append(command)

    cut_clips(
        prepared_video,
        [clip],
        runner=fake_runner,
        clip_padding=ClipPadding(pre_seconds=10, post_seconds=10),
    )

    assert len(commands) == 4
    assert [command[command.index("-ss") + 1] for command in commands[:3]] == ["90", "98", "208"]
    assert [command[command.index("-t") + 1] for command in commands[:3]] == ["5", "107", "2"]


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



def test_cut_clip_passes_ffmpeg_arguments_as_list_and_uses_utf8(tmp_path) -> None:
    input_path = tmp_path / "input.mp4"
    output_path = tmp_path / "ريلز" / "مقطع.mp4"
    input_path.write_bytes(b"video")
    output_path.parent.mkdir()
    output_path.write_bytes(b"output")
    calls = []

    def fake_runner(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="ffmpeg normal progress")

    result = cut_clip(input_path, output_path, 0, 10, runner=fake_runner)

    assert result == output_path
    assert isinstance(calls[0][0], list)
    assert calls[0][1]["check"] is False
    assert calls[0][1]["capture_output"] is True
    assert calls[0][1]["text"] is True
    assert calls[0][1]["encoding"] == "utf-8"
    assert calls[0][1]["errors"] == "replace"


def test_cut_clip_does_not_fail_just_because_ffmpeg_writes_to_stderr(tmp_path) -> None:
    input_path = tmp_path / "input.mp4"
    output_path = tmp_path / "output.mp4"
    input_path.write_bytes(b"video")
    output_path.write_bytes(b"output")

    def fake_runner(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="ffmpeg writes normal info to stderr")

    assert cut_clip(input_path, output_path, 0, 10, runner=fake_runner) == output_path


def test_cut_clip_rejects_signal_15_even_when_output_exists(tmp_path) -> None:
    input_path = tmp_path / "input.mp4"
    output_path = tmp_path / "output.mp4"
    input_path.write_bytes(b"video")
    output_path.write_bytes(b"partial but incomplete output")

    def fake_runner(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            255,
            stdout="",
            stderr="Exiting normally, received signal 15",
        )

    with pytest.raises(Exception) as error:
        cut_clip(input_path, output_path, 0, 10, runner=fake_runner)

    assert "signal 15" in str(error.value).lower()


def test_cut_clip_rejects_successful_run_when_output_is_partial(tmp_path, monkeypatch) -> None:
    input_path = tmp_path / "input.mp4"
    output_path = tmp_path / "output.mp4"
    input_path.write_bytes(b"video")
    output_path.write_bytes(b"x")
    monkeypatch.setattr("src.video_processor._should_validate_media_duration", lambda runner: True)

    def fake_runner(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    with pytest.raises(Exception) as error:
        cut_clip(input_path, output_path, 0, 10, runner=fake_runner)

    assert "فارغ" in str(error.value)


def test_cut_clip_missing_ffmpeg_raises_clear_arabic_error(tmp_path) -> None:
    input_path = tmp_path / "input.mp4"
    output_path = tmp_path / "output.mp4"
    input_path.write_bytes(b"video")

    def fake_runner(command, **kwargs):
        raise FileNotFoundError("ffmpeg")

    with pytest.raises(FfmpegNotFoundError) as error:
        cut_clip(input_path, output_path, 0, 10, runner=fake_runner)

    assert str(error.value) == AR_FFMPEG_NOT_FOUND


def test_cut_clip_failure_error_is_concise(tmp_path) -> None:
    input_path = tmp_path / "input.mp4"
    output_path = tmp_path / "output.mp4"
    input_path.write_bytes(b"video")
    long_stderr = "\n".join([
        "ffmpeg version 8.1.1-full_build-www.gyan.dev",
        "configuration: lots of build flags",
        "Input #0, mov, from input.mp4",
        "Stream #0:0 Video",
        "Conversion failed: Invalid argument",
    ])

    def fake_runner(command, **kwargs):
        return subprocess.CompletedProcess(command, 1, stdout="", stderr=long_stderr)

    with pytest.raises(Exception) as error:
        cut_clip(input_path, output_path, 0, 10, runner=fake_runner)

    message = str(error.value)
    assert "Invalid argument" in message
    assert "configuration:" not in message
    assert "ffmpeg version" not in message


def test_download_youtube_video_emits_progress_messages(tmp_path) -> None:
    destination = tmp_path / "input.mp4"
    messages: list[str] = []
    captured_options: dict = {}

    class FakeYoutubeDL:
        def __init__(self, options):
            captured_options.update(options)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def download(self, urls):
            hook = captured_options["progress_hooks"][0]
            hook({"status": "downloading", "downloaded_bytes": 50, "total_bytes": 100})
            hook({"status": "finished"})
            destination.write_bytes(b"video")

    result = download_youtube_video("https://youtu.be/example", destination, FakeYoutubeDL, messages.append)

    assert result == destination
    assert destination.read_bytes() == b"video"
    assert "جاري قراءة معلومات الفيديو" in messages
    assert "جاري تنزيل الفيديو: 50%" in messages
    assert "اكتمل تنزيل الفيديو، جاري تجهيز الملف" in messages
    assert captured_options["progress_hooks"]
    assert captured_options["socket_timeout"] == 30


def test_download_youtube_video_keeps_best_video_best_audio_and_cookies_disabled_by_default(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr("src.video_processor.bundled_ffmpeg_location", lambda: None)

    options = _capture_youtube_options(tmp_path)

    assert options["format"] == YOUTUBE_BEST_VIDEO_AUDIO_FORMAT
    assert "cookiesfrombrowser" not in options
    assert options["merge_output_format"] == "mp4"
    assert options["noplaylist"] is True


@pytest.mark.parametrize(
    ("browser", "expected_cookie_browser"),
    [
        ("Chrome", "chrome"),
        ("Edge", "edge"),
        ("Brave", "brave"),
        ("Firefox", "firefox"),
    ],
)
def test_download_youtube_video_passes_browser_cookies_when_enabled(
    tmp_path,
    monkeypatch,
    browser: str,
    expected_cookie_browser: str,
) -> None:
    monkeypatch.setattr("src.video_processor.bundled_ffmpeg_location", lambda: None)

    options = _capture_youtube_options(
        tmp_path,
        use_browser_cookies=True,
        browser=browser,
    )

    assert options["cookiesfrombrowser"] == (expected_cookie_browser,)


def test_download_youtube_video_passes_ffmpeg_location_when_bundled_ffmpeg_exists(
    tmp_path,
    monkeypatch,
) -> None:
    bundled_tools_folder = tmp_path / "tools"
    bundled_tools_folder.mkdir()
    monkeypatch.setattr("src.video_processor.bundled_ffmpeg_location", lambda: str(bundled_tools_folder))

    options = _capture_youtube_options(tmp_path)

    assert options["ffmpeg_location"] == str(bundled_tools_folder)


def test_verify_output_duration_rejects_short_partial_clip(tmp_path, monkeypatch) -> None:
    output_path = tmp_path / "partial.mp4"
    output_path.write_bytes(b"not a real video but probe is mocked")

    monkeypatch.setattr("src.video_processor.probe_media_duration_seconds", lambda path: 10.0)

    with pytest.raises(Exception) as error:
        verify_output_duration(output_path, 80)

    assert "أقصر من المطلوب" in str(error.value)


def test_verify_output_duration_accepts_near_expected_duration(tmp_path, monkeypatch) -> None:
    output_path = tmp_path / "ok.mp4"
    output_path.write_bytes(b"not a real video but probe is mocked")

    monkeypatch.setattr("src.video_processor.probe_media_duration_seconds", lambda path: 79.2)

    verify_output_duration(output_path, 80)
