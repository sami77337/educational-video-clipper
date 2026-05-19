"""Smart paste parser for real-world Arabic clip request messages.

This parser is intentionally preview-only. It extracts likely video URLs,
project/title text, clip ranges, warnings, and unparsed lines without touching
the current table import, download, or cutting workflows.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.time_utils import normalize_digits, normalize_time_symbols, normalize_timestamp_text


_TIME_PATTERN = r"\d{1,3}:\d{1,2}(?::\d{1,2})?"
_RANGE_SEPARATOR_PATTERN = r"(?:[-–—]|إلى|الى|إلي|الي)"
_RANGE_PATTERN = re.compile(
    rf"(?:من\s+(?:الدقيقة\s+)?)?"
    rf"\[?\s*({_TIME_PATTERN})\s*\]?"
    rf"\s*{_RANGE_SEPARATOR_PATTERN}\s*"
    rf"(?:الدقيقة\s+)?"
    rf"\[?\s*({_TIME_PATTERN})\s*\]?"
)
_YOUTUBE_URL_PATTERN = re.compile(
    r"https?://(?:www\.|m\.)?"
    r"(?:youtube\.com/(?:watch\?[^\s<>()\[\]]+|live/[^\s<>()\[\]]+|shorts/[^\s<>()\[\]]+)"
    r"|youtu\.be/[^\s<>()\[\]]+)",
    re.IGNORECASE,
)
_WHATSAPP_METADATA_PATTERN = re.compile(r"^\[[^\]]+\]\s*[^:]{1,80}:\s*")
_INTERNAL_RANGE_IN_PARENTHESES_PATTERN = re.compile(
    rf"\(\s*{_TIME_PATTERN}\s*{_RANGE_SEPARATOR_PATTERN}\s*{_TIME_PATTERN}\s*\)"
)
_PLUS_JOINED_RANGE_PATTERN = re.compile(
    rf"{_TIME_PATTERN}\s*{_RANGE_SEPARATOR_PATTERN}\s*{_TIME_PATTERN}\s*\+\s*"
    rf"{_TIME_PATTERN}\s*{_RANGE_SEPARATOR_PATTERN}\s*{_TIME_PATTERN}"
)
_INTERNAL_CUT_PHRASES = (
    "مابين القوسين يقطع",
    "ما بين القوسين يقطع",
    "مابين القوسين",
    "ما بين القوسين",
    "احذف",
    "يقطع",
)
_WORD_MARKER_PHRASES = (
    "أول كلمة",
    "اول كلمة",
    "آخر كلمة",
    "اخر كلمة",
    "كلمة البداية",
    "كلمة النهاية",
    "من كلمة",
    "إلى كلمة",
    "الى كلمة",
)


@dataclass(frozen=True)
class SmartPasteClip:
    """One parsed clip candidate for preview."""

    number: int
    title: str
    start: str
    end: str
    line_number: int
    raw_line: str


@dataclass(frozen=True)
class SmartPasteWarning:
    """A non-fatal parser warning."""

    line_number: int
    message_ar: str
    raw_line: str


@dataclass(frozen=True)
class SmartPasteUnparsedLine:
    """A line that was not understood as URL, title, or clip data."""

    line_number: int
    raw_line: str


@dataclass(frozen=True)
class SmartPastePreview:
    """Preview result returned by the smart paste parser."""

    video_urls: list[str]
    project_title: str
    clips: list[SmartPasteClip]
    warnings: list[SmartPasteWarning]
    unparsed_lines: list[SmartPasteUnparsedLine]


@dataclass(frozen=True)
class _LineContext:
    line_number: int
    raw_line: str
    text: str


@dataclass(frozen=True)
class _ClipCandidate:
    title: str
    start: str
    end: str


def parse_smart_paste_message(raw_text: str | None) -> SmartPastePreview:
    """Parse a pasted message into preview data without applying it to the app."""

    video_urls: list[str] = []
    clips: list[SmartPasteClip] = []
    warnings: list[SmartPasteWarning] = []
    unparsed_lines: list[SmartPasteUnparsedLine] = []
    project_title = ""

    for line_number, raw_line in enumerate(str(raw_text or "").splitlines(), start=1):
        context = _prepare_line(raw_line, line_number)
        if context is None:
            continue

        line_urls = _extract_youtube_urls(context.text)
        for url in line_urls:
            if url not in video_urls:
                video_urls.append(url)
        line_without_urls = _remove_urls(context.text).strip()
        if not line_without_urls:
            continue

        context = _LineContext(context.line_number, context.raw_line, line_without_urls)
        unsupported_warnings = _detect_unsupported_patterns(context)
        if _has_plus_joined_ranges(context.text):
            warnings.extend(unsupported_warnings)
            unparsed_lines.append(SmartPasteUnparsedLine(context.line_number, context.raw_line))
            continue

        candidate = _parse_begin_end_clip(context.text) or _parse_range_clip(context.text)
        if candidate is not None:
            warnings.extend(unsupported_warnings)
            clip_number = len(clips) + 1
            clips.append(
                SmartPasteClip(
                    number=clip_number,
                    title=candidate.title or f"مقطع {clip_number:02d}",
                    start=candidate.start,
                    end=candidate.end,
                    line_number=context.line_number,
                    raw_line=context.raw_line,
                )
            )
            continue

        if unsupported_warnings:
            warnings.extend(unsupported_warnings)
            unparsed_lines.append(SmartPasteUnparsedLine(context.line_number, context.raw_line))
            continue

        if not project_title and _looks_like_project_title(context.text):
            project_title = _clean_title(context.text)
            continue

        unparsed_lines.append(SmartPasteUnparsedLine(context.line_number, context.raw_line))

    return SmartPastePreview(
        video_urls=video_urls,
        project_title=project_title,
        clips=clips,
        warnings=warnings,
        unparsed_lines=unparsed_lines,
    )


def _prepare_line(raw_line: str, line_number: int) -> _LineContext | None:
    stripped = str(raw_line).strip()
    if not stripped:
        return None

    stripped = _WHATSAPP_METADATA_PATTERN.sub("", stripped).strip()
    if not stripped:
        return None

    try:
        normalized = normalize_time_symbols(stripped)
    except ValueError:
        return None

    return _LineContext(line_number=line_number, raw_line=raw_line, text=normalized)


def _extract_youtube_urls(text: str) -> list[str]:
    return [_clean_url(match.group(0)) for match in _YOUTUBE_URL_PATTERN.finditer(text)]


def _remove_urls(text: str) -> str:
    return _YOUTUBE_URL_PATTERN.sub(" ", text)


def _clean_url(url: str) -> str:
    return url.rstrip(".,،؛:)]}؟")


def _parse_range_clip(text: str) -> _ClipCandidate | None:
    match = _RANGE_PATTERN.search(text)
    if match is None:
        return None

    start = _normalize_time(match.group(1))
    end = _normalize_time(match.group(2))
    if start is None or end is None:
        return None

    prefix = _strip_number_prefix(text[: match.start()])
    suffix = text[match.end() :]
    title = _clean_title(prefix) or _clean_title(suffix)
    return _ClipCandidate(title=title, start=start, end=end)


def _parse_begin_end_clip(text: str) -> _ClipCandidate | None:
    begin_match = re.search(r"البداية\s*:?", text)
    end_match = re.search(r"النهاية\s*:?", text)
    if begin_match is None or end_match is None or end_match.start() <= begin_match.end():
        return None

    prefix = _strip_number_prefix(text[: begin_match.start()])
    begin_segment = text[begin_match.end() : end_match.start()]
    end_segment = text[end_match.end() :]
    start_marker = _extract_time_and_remaining_text(begin_segment)
    end_marker = _extract_time_and_remaining_text(end_segment)
    if start_marker is None or end_marker is None:
        return None

    start, start_title = start_marker
    end, end_title = end_marker
    title = _clean_title(prefix) or _clean_title(start_title) or _clean_title(end_title)
    return _ClipCandidate(title=title, start=start, end=end)


def _extract_time_and_remaining_text(text: str) -> tuple[str, str] | None:
    match = re.search(_TIME_PATTERN, text)
    if match is None:
        return None

    timestamp = _normalize_time(match.group(0))
    if timestamp is None:
        return None

    remaining_text = f"{text[: match.start()]} {text[match.end() :]}"
    return timestamp, remaining_text


def _detect_unsupported_patterns(context: _LineContext) -> list[SmartPasteWarning]:
    warnings: list[SmartPasteWarning] = []
    text = context.text

    if _has_internal_cut_pattern(text):
        warnings.append(
            SmartPasteWarning(
                context.line_number,
                f"تحذير في السطر {context.line_number}: تم اكتشاف حذف داخلي ولم يتم تحليله في هذا الإصدار",
                context.raw_line,
            )
        )

    if _has_plus_joined_ranges(text):
        warnings.append(
            SmartPasteWarning(
                context.line_number,
                f"تحذير في السطر {context.line_number}: المقاطع متعددة الأجزاء بعلامة + غير مدعومة في هذا الإصدار",
                context.raw_line,
            )
        )

    if any(phrase in text for phrase in _WORD_MARKER_PHRASES):
        warnings.append(
            SmartPasteWarning(
                context.line_number,
                f"تحذير في السطر {context.line_number}: علامات أول كلمة وآخر كلمة غير مدعومة في هذا الإصدار",
                context.raw_line,
            )
        )

    return warnings


def _has_internal_cut_pattern(text: str) -> bool:
    if _INTERNAL_RANGE_IN_PARENTHESES_PATTERN.search(text):
        return True
    range_count = len(list(_RANGE_PATTERN.finditer(text)))
    return range_count > 1 and any(phrase in text for phrase in _INTERNAL_CUT_PHRASES)


def _has_plus_joined_ranges(text: str) -> bool:
    return _PLUS_JOINED_RANGE_PATTERN.search(text) is not None


def _normalize_time(value: str) -> str | None:
    try:
        return normalize_timestamp_text(value)
    except ValueError:
        return None


def _strip_number_prefix(text: str) -> str:
    text = normalize_digits(str(text))
    text = re.sub(r"^\s*\d+\s*[-–—.)]\s*", "", text)
    return text


def _clean_title(value: str) -> str:
    title = normalize_digits(str(value))
    title = _YOUTUBE_URL_PATTERN.sub(" ", title)
    title = _INTERNAL_RANGE_IN_PARENTHESES_PATTERN.sub(" ", title)
    for phrase in _INTERNAL_CUT_PHRASES:
        title = title.replace(phrase, " ")
    title = re.sub(r"\s+", " ", title).strip(" :：-–—,،؛()[]")
    if title.startswith("(") and title.endswith(")"):
        title = title[1:-1].strip()
    return title


def _looks_like_project_title(text: str) -> bool:
    if _RANGE_PATTERN.search(text) or re.search(_TIME_PATTERN, text):
        return False
    if _extract_youtube_urls(text):
        return False
    cleaned = _clean_title(text)
    return bool(cleaned) and len(cleaned) >= 3
