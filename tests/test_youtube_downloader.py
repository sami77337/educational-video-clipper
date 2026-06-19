import pytest
from yt_dlp.utils import DownloadError

from src.video.youtube_downloader import (
    AR_EMPTY_YOUTUBE_URL,
    YOUTUBE_BEST_VIDEO_AUDIO_FORMAT,
    YouTubeDownloadError,
    download_youtube_video,
    normalize_browser_name,
    validate_youtube_url,
)


def _capture_youtube_options(tmp_path, **download_kwargs) -> tuple[dict, list[str]]:
    destination = tmp_path / "input.mp4"
    captured_options: dict = {}
    messages: list[str] = []

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

    download_youtube_video(
        "https://youtu.be/example",
        destination,
        FakeYoutubeDL,
        messages.append,
        ffmpeg_location_provider=lambda: None,
        **download_kwargs,
    )
    return captured_options, messages


def test_validate_youtube_url_rejects_empty_value() -> None:
    with pytest.raises(YouTubeDownloadError) as error:
        validate_youtube_url("   ")

    assert str(error.value) == AR_EMPTY_YOUTUBE_URL


def test_download_youtube_video_keeps_best_video_best_audio_and_cookies_disabled_by_default(tmp_path) -> None:
    options, _messages = _capture_youtube_options(tmp_path)

    assert options["format"] == YOUTUBE_BEST_VIDEO_AUDIO_FORMAT
    assert "cookiesfrombrowser" not in options
    assert options["merge_output_format"] == "mp4"
    assert options["retries"] == 10
    assert options["fragment_retries"] == 10
    assert options["socket_timeout"] == 30
    assert options["concurrent_fragment_downloads"] == 8


@pytest.mark.parametrize(
    ("browser", "expected_browser"),
    [
        ("Chrome", "chrome"),
        ("Edge", "edge"),
        ("Brave", "brave"),
        ("Firefox", "firefox"),
    ],
)
def test_download_youtube_video_passes_browser_cookies_when_enabled(tmp_path, browser: str, expected_browser: str) -> None:
    options, messages = _capture_youtube_options(tmp_path, use_browser_cookies=True, browser=browser)

    assert options["cookiesfrombrowser"] == (expected_browser,)
    assert f"سيتم استخدام تسجيل الدخول من المتصفح لتنزيل يوتيوب: {expected_browser}" in messages


def test_normalize_browser_name_falls_back_to_chrome_for_unknown_browser() -> None:
    assert normalize_browser_name("unknown") == "chrome"


def test_download_youtube_video_passes_ffmpeg_location_when_available(tmp_path) -> None:
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
            destination.write_bytes(b"video")

    download_youtube_video(
        "https://youtu.be/example",
        destination,
        FakeYoutubeDL,
        ffmpeg_location_provider=lambda: str(tmp_path / "tools"),
    )

    assert captured_options["ffmpeg_location"] == str(tmp_path / "tools")


def test_download_youtube_video_progress_hook_reports_progress(tmp_path) -> None:
    _options, messages = _capture_youtube_options(tmp_path)

    assert "جاري قراءة معلومات الفيديو" in messages
    assert "جاري تنزيل الفيديو: 50%" in messages
    assert "اكتمل تنزيل الفيديو، جاري تجهيز الملف" in messages


def test_youtube_bot_sign_in_error_is_translated_to_arabic(tmp_path) -> None:
    destination = tmp_path / "input.mp4"

    class FakeYoutubeDL:
        def __init__(self, options):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def download(self, urls):
            raise DownloadError("Sign in to confirm you're not a bot")

    with pytest.raises(YouTubeDownloadError) as error:
        download_youtube_video(
            "https://youtu.be/example",
            destination,
            FakeYoutubeDL,
            ffmpeg_location_provider=lambda: None,
        )

    assert "تعذر تنزيل الفيديو من يوتيوب بسبب تحقق يوتيوب" in str(error.value)
