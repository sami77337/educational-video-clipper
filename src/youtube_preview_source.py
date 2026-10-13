"""Cache an authorized YouTube video for local clip review without stale-source reuse."""
from __future__ import annotations

import json
import os
from pathlib import Path

from src.gemini_import import normalize_youtube_video_url


CACHE_METADATA = ".prepared_youtube_source.json"
MIN_SOURCE_BYTES = 1024


def cached_youtube_video(video: str | Path, source_url: str) -> bool:
    """Reuse only if a nonempty MP4 matches the exact YouTube video identity."""
    source = normalize_youtube_video_url(source_url)
    video_path = Path(video)
    if source is None or not video_path.is_file():
        return False
    try:
        if video_path.stat().st_size < MIN_SOURCE_BYTES:
            return False
        metadata = video_path.parent / CACHE_METADATA
        if not metadata.is_file() or metadata.stat().st_size > 2048:
            return False
        data = json.loads(metadata.read_text(encoding="utf-8"))
        return data.get("source_url") == source
    except (OSError, ValueError, TypeError, AttributeError):
        return False


def remember_youtube_source(video: str | Path, source_url: str) -> None:
    """Record video ID only after a successful authorized download."""
    canonical = normalize_youtube_video_url(source_url)
    if not canonical:
        raise ValueError("رابط يوتيوب غير صحيح.")
    path = Path(video)
    if not path.is_file() or path.stat().st_size < MIN_SOURCE_BYTES:
        raise ValueError("ملف الفيديو غير جاهز.")
    marker = path.parent / CACHE_METADATA
    temp = marker.with_suffix(".tmp")
    try:
        temp.write_text(
            json.dumps({"source_url": canonical}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        os.replace(temp, marker)
    finally:
        temp.unlink(missing_ok=True)
