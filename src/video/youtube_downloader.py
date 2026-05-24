"""YouTube download helpers built on yt-dlp."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from src.file_utils import ensure_directory
from src.video.ffmpeg_runner import bundled_ffmpeg_location


AR_EMPTY_YOUTUBE_URL = "خطأ: رابط يوتيوب فارغ"
AR_YOUTUBE_READING_INFO = "جاري قراءة معلومات الفيديو"
AR_YOUTUBE_DOWNLOAD_PROGRESS = "جاري تنزيل الفيديو"
AR_YOUTUBE_DOWNLOAD_FINISHING = "اكتمل تنزيل الفيديو، جاري تجهيز الملف"
AR_USING_BROWSER_COOKIES = "سيتم استخدام تسجيل الدخول من المتصفح لتنزيل يوتيوب"
AR_BROWSER_COOKIES_FAILED = "تعذر قراءة تسجيل الدخول من المتصفح. أغلق المتصفح ثم حاول مرة أخرى، أو اختر فيديو من الجهاز."
AR_YOUTUBE_FORMAT_FALLBACK_FAILED = "فشل تحميل الفيديو من يوتيوب بعد تجربة عدة صيغ. قد يكون الفيديو مقيدًا أو يحتاج تسجيل دخول أو Cookies."
AR_YOUTUBE_LOGIN_OR_COOKIES_NEEDED = "قد يحتاج هذا الفيديو إلى تسجيل دخول أو استخدام Cookies من المتصفح."
AR_YOUTUBE_DOWNLOAD_FAILED = "فشل تحميل الفيديو من يوتيوب"
AR_YOUTUBE_FORMAT_ATTEMPT = "محاولة تحميل يوتيوب بصيغة"
AR_YOUTUBE_FORMAT_SUCCESS = "نجح تحميل يوتيوب باستخدام الصيغة"

YOUTUBE_FORMAT_FALLBACKS = [
    "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080][ext=mp4]/best[height<=1080][ext=mp4]",
    "bv*[height<=1080]+ba/b[height<=1080]/best[height<=1080]",
    "bv*+ba/bestvideo+bestaudio/best",
    "best",
]
YOUTUBE_BEST_VIDEO_AUDIO_FORMAT = YOUTUBE_FORMAT_FALLBACKS[0]
YOUTUBE_DOWNLOAD_SUFFIXES = (".mp4", ".webm", ".mkv")

ProgressCallback = Callable[[str], None]
YoutubeDlFactory = Callable[[dict[str, Any]], Any]
FfmpegLocationProvider = Callable[[], str | None]


class YouTubeDownloadError(ValueError):
    """Raised when YouTube URL validation or translated yt-dlp errors fail."""


def validate_youtube_url(url: str | None) -> str:
    """Validate that a YouTube URL was provided."""

    if url is None or not url.strip():
        raise YouTubeDownloadError(AR_EMPTY_YOUTUBE_URL)

    return url.strip()


def normalize_browser_name(browser: str | None) -> str:
    """Return a yt-dlp browser identifier supported by the UI."""

    value = (browser or "chrome").strip().lower()
    aliases = {
        "chrome": "chrome",
        "google chrome": "chrome",
        "edge": "edge",
        "microsoft edge": "edge",
        "brave": "brave",
        "firefox": "firefox",
    }
    return aliases.get(value, "chrome")


def download_youtube_video(
    url: str,
    destination: str | Path,
    youtube_dl_factory: YoutubeDlFactory = YoutubeDL,
    progress_callback: ProgressCallback | None = None,
    *,
    use_browser_cookies: bool = False,
    browser: str = "chrome",
    ffmpeg_location_provider: FfmpegLocationProvider = bundled_ffmpeg_location,
) -> Path:
    """Download a YouTube video to the given destination using yt-dlp's Python API.

    yt-dlp can spend noticeable time extracting metadata and downloading large
    video/audio streams. Emit progress messages from yt-dlp hooks so the UI does
    not look frozen while the worker is still active.
    """

    destination_path = Path(destination)
    ensure_directory(destination_path.parent)

    progress_hook = _build_youtube_progress_hook(progress_callback)
    _emit(progress_callback, "يتم تنزيل أفضل جودة فيديو وأفضل جودة صوت")
    _emit(progress_callback, AR_YOUTUBE_READING_INFO)

    # Keep high quality while allowing retries when YouTube does not expose one
    # requested format. Later fallbacks may produce mp4, webm, or mkv.
    base_options = {
        "noplaylist": True,
        "outtmpl": str(_download_output_template(destination_path)),
        "overwrites": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "retries": 10,
        "fragment_retries": 10,
        "socket_timeout": 30,
        "continuedl": True,
        # Speed up fragmented YouTube streams when available without changing
        # selected video/audio formats. This only downloads multiple fragments
        # at the same time; final quality remains bestvideo+bestaudio.
        "concurrent_fragment_downloads": 8,
        "progress_hooks": [progress_hook],
    }

    ffmpeg_location = ffmpeg_location_provider()
    if ffmpeg_location:
        base_options["ffmpeg_location"] = ffmpeg_location

    if use_browser_cookies:
        selected_browser = normalize_browser_name(browser)
        base_options["cookiesfrombrowser"] = (selected_browser,)
        _emit(progress_callback, f"{AR_USING_BROWSER_COOKIES}: {selected_browser}")

    last_format_error: DownloadError | None = None
    for index, selector in enumerate(YOUTUBE_FORMAT_FALLBACKS):
        _cleanup_download_attempt_files(destination_path)
        options = dict(base_options)
        options["format"] = selector
        if index == 0:
            options["merge_output_format"] = "mp4"
        _emit(progress_callback, f"{AR_YOUTUBE_FORMAT_ATTEMPT}: {selector}")
        try:
            with youtube_dl_factory(options) as ydl:
                ydl.download([url])
        except DownloadError as error:
            if _is_format_unavailable_error(error):
                last_format_error = error
                continue
            raise _translate_youtube_download_error(error, use_browser_cookies) from error

        downloaded_path = _find_downloaded_video(destination_path)
        _emit(progress_callback, f"{AR_YOUTUBE_FORMAT_SUCCESS}: {selector}")
        return downloaded_path

    if last_format_error is not None:
        raise YouTubeDownloadError(AR_YOUTUBE_FORMAT_FALLBACK_FAILED) from last_format_error
    raise YouTubeDownloadError(AR_YOUTUBE_FORMAT_FALLBACK_FAILED)


def _download_output_template(destination_path: Path) -> Path:
    return destination_path.with_suffix(".%(ext)s")


def _cleanup_download_attempt_files(destination_path: Path) -> None:
    for path in destination_path.parent.glob(f"{destination_path.stem}.*"):
        if path.is_file():
            try:
                path.unlink()
            except OSError:
                pass


def _find_downloaded_video(destination_path: Path) -> Path:
    if destination_path.is_file():
        return destination_path

    candidates = [
        path
        for path in destination_path.parent.glob(f"{destination_path.stem}.*")
        if path.is_file() and path.suffix.lower() in YOUTUBE_DOWNLOAD_SUFFIXES
    ]
    if not candidates:
        return destination_path
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _is_format_unavailable_error(error: DownloadError) -> bool:
    message = str(error).lower()
    return (
        "requested format is not available" in message
        or "format is not available" in message
        or "requested format not available" in message
    )


def _translate_youtube_download_error(error: DownloadError, use_browser_cookies: bool) -> YouTubeDownloadError:
    error_text = str(error)
    lowered = error_text.lower()
    if use_browser_cookies and ("cookie" in lowered or "browser" in lowered or "database" in lowered):
        return YouTubeDownloadError(AR_BROWSER_COOKIES_FAILED)
    if _looks_like_login_or_cookie_error(lowered):
        return YouTubeDownloadError(
            f"تعذر تنزيل الفيديو من يوتيوب بسبب تحقق يوتيوب. {AR_YOUTUBE_LOGIN_OR_COOKIES_NEEDED}"
        )
    return YouTubeDownloadError(f"{AR_YOUTUBE_DOWNLOAD_FAILED}: {error_text}")


def _looks_like_login_or_cookie_error(lowered_error_text: str) -> bool:
    return (
        "sign in to confirm" in lowered_error_text
        or "not a bot" in lowered_error_text
        or "login" in lowered_error_text
        or "cookies" in lowered_error_text
        or "cookie" in lowered_error_text
    )


def _build_youtube_progress_hook(progress_callback: ProgressCallback | None) -> Callable[[dict[str, Any]], None]:
    """Build a throttled yt-dlp progress hook with useful Arabic messages.

    Some YouTube downloads report many early progress events with 0% because
    yt-dlp has not yet received a reliable total size or because the file is
    large. Showing repeated 0% messages makes the app look stuck. Instead,
    throttle messages and show downloaded MB / speed when percentage is not yet
    meaningful.
    """

    state: dict[str, Any] = {
        "last_percent": -1,
        "last_downloaded_mb": -1.0,
        "last_emit_time": 0.0,
        "last_message": "",
        "sent_downloading": False,
    }

    def should_emit(message: str, force: bool = False) -> bool:
        now = time.monotonic()
        if force:
            state["last_emit_time"] = now
            state["last_message"] = message
            return True
        if message == state["last_message"]:
            return False
        if now - state["last_emit_time"] < 1.0:
            return False
        state["last_emit_time"] = now
        state["last_message"] = message
        return True

    def hook(data: dict[str, Any]) -> None:
        status = data.get("status")
        if status == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate")
            downloaded = data.get("downloaded_bytes") or 0
            downloaded_mb = downloaded / (1024 * 1024) if downloaded else 0.0
            speed = data.get("speed") or 0
            speed_mb = speed / (1024 * 1024) if speed else 0.0
            eta = data.get("eta")

            if total:
                total_mb = total / (1024 * 1024)
                percent = int(min(100, max(0, (downloaded / total) * 100)))
                state["sent_downloading"] = True

                # Do not spam repeated 0%. At 0%, show MB progress instead.
                if percent <= 0:
                    message = f"{AR_YOUTUBE_DOWNLOAD_PROGRESS}: {downloaded_mb:.1f} MB"
                elif total_mb >= 1:
                    message = (
                        f"{AR_YOUTUBE_DOWNLOAD_PROGRESS}: {percent}% "
                        f"({downloaded_mb:.1f}/{total_mb:.1f} MB)"
                    )
                else:
                    message = f"{AR_YOUTUBE_DOWNLOAD_PROGRESS}: {percent}%"

                if speed_mb > 0:
                    message += f" - {speed_mb:.1f} MB/s"
                if eta is not None:
                    message += f" - المتبقي: {eta} ثانية"

                # Emit early once, then every meaningful percent change or MB jump.
                percent_changed = percent > state["last_percent"] and (percent - state["last_percent"] >= 2)
                mb_changed = downloaded_mb - state["last_downloaded_mb"] >= 5
                if percent <= 0:
                    percent_changed = False
                if should_emit(message, force=(state["last_percent"] < 0 or percent == 100 or percent_changed or mb_changed)):
                    state["last_percent"] = percent
                    state["last_downloaded_mb"] = downloaded_mb
                    _emit(progress_callback, message)
            else:
                message = f"{AR_YOUTUBE_DOWNLOAD_PROGRESS}: {downloaded_mb:.1f} MB"
                if speed_mb > 0:
                    message += f" - {speed_mb:.1f} MB/s"
                if should_emit(message, force=not state["sent_downloading"]):
                    state["sent_downloading"] = True
                    state["last_downloaded_mb"] = downloaded_mb
                    _emit(progress_callback, message)
        elif status == "finished":
            _emit(progress_callback, AR_YOUTUBE_DOWNLOAD_FINISHING)
        elif status == "error":
            _emit(progress_callback, "حدث خطأ أثناء تنزيل الفيديو من يوتيوب")

    return hook


def _emit(progress_callback: ProgressCallback | None, message: str) -> None:
    if progress_callback is not None:
        progress_callback(message)
