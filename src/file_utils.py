"""File-related helpers."""

from __future__ import annotations

import re
from pathlib import Path


_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*]+')


def ensure_directory(path: str | Path) -> Path:
    """Create a directory if needed and return it as a Path."""

    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def sanitize_filename(name: str, default: str = "clip") -> str:
    """Return a Windows-safe filename stem."""

    cleaned = _INVALID_FILENAME_CHARS.sub("-", name).strip(" .-")
    return cleaned or default
