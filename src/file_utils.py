"""File-related helpers."""

from __future__ import annotations

import re
from pathlib import Path


_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*]+')
_CONTROL_WHITESPACE_CHARS = re.compile(r"[\t\n\r\f\v]+")
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]+")
_WHITESPACE = re.compile(r"\s+")
DEFAULT_MAX_FILENAME_LENGTH = 80


def ensure_directory(path: str | Path) -> Path:
    """Create a directory if needed and return it as a Path."""

    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def sanitize_filename(
    name: str | None,
    default: str = "clip",
    max_length: int = DEFAULT_MAX_FILENAME_LENGTH,
) -> str:
    """Return a Windows-safe filename stem."""

    cleaned = "" if name is None else str(name)
    cleaned = _CONTROL_WHITESPACE_CHARS.sub(" ", cleaned)
    cleaned = _CONTROL_CHARS.sub("", cleaned)
    cleaned = _INVALID_FILENAME_CHARS.sub("-", cleaned)
    cleaned = _WHITESPACE.sub(" ", cleaned).strip(" .-")

    if max_length > 0:
        cleaned = cleaned[:max_length].strip(" .-")

    if cleaned:
        return cleaned
    if max_length > 0:
        return default[:max_length]
    return default
