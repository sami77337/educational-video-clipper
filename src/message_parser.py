"""Parse pasted Arabic clip request messages into table rows."""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.time_utils import normalize_digits, normalize_time_symbols, normalize_timestamp_text


AR_UNPARSEABLE_LINE = "تعذر فهم السطر"

_TIME_PATTERN = r"\d{1,3}:\d{1,2}(?::\d{1,2})?"
_RANGE_PATTERN = re.compile(
    rf"\[?\s*({_TIME_PATTERN})\s*\]?\s*[-–—]\s*\[?\s*({_TIME_PATTERN})\s*\]?"
)
_INTERNAL_RANGE_PATTERN = re.compile(
    rf"\(\s*{_TIME_PATTERN}\s*[-–—]\s*{_TIME_PATTERN}\s*\)"
)
_ARABIC_ORDINALS = {
    "الأول": 1,
    "الاول": 1,
    "أول": 1,
    "اول": 1,
    "الثاني": 2,
    "الثالث": 3,
    "الرابع": 4,
    "الخامس": 5,
    "السادس": 6,
    "السابع": 7,
    "الثامن": 8,
    "التاسع": 9,
    "العاشر": 10,
}
_NOTE_PREFIXES = (
    "*",
    "ملاحظة",
    "يحتاج",
    "تحركت الكاميرا",
    "تحركت الكميرا",
)


@dataclass(frozen=True)
class ParsedClipLine:
    """One parsed pasted clip line."""

    number: int
    title: str
    start: str
    end: str


@dataclass(frozen=True)
class ParseWarning:
    """A line-level parser warning suitable for Arabic UI logs."""

    line_number: int
    raw_line: str

    @property
    def message_ar(self) -> str:
        return f"{AR_UNPARSEABLE_LINE} {self.line_number}"


@dataclass(frozen=True)
class ParseResult:
    """Parsed clips and non-fatal warnings."""

    clips: list[ParsedClipLine]
    warnings: list[ParseWarning]


@dataclass(frozen=True)
class _ClipCandidate:
    number: int | None
    title: str
    start: str
    end: str


@dataclass(frozen=True)
class _PendingTitle:
    line_number: int
    raw_line: str
    number: int | None
    title: str


@dataclass
class _BeginEndBlock:
    line_number: int
    raw_line: str
    number: int | None
    title: str
    start: str | None = None
    start_title: str = ""
    end: str | None = None
    end_title: str = ""


def parse_clip_message(message: str) -> ParseResult:
    """Parse pasted plain text into clips and warnings."""

    clips: list[ParsedClipLine] = []
    warnings: list[ParseWarning] = []
    pending_title: _PendingTitle | None = None
    block: _BeginEndBlock | None = None
    next_auto_number = 1

    for line_number, raw_line in enumerate(message.splitlines(), start=1):
        if not raw_line.strip():
            continue

        line = _normalize_line(raw_line)
        if not line or _is_note_line(line):
            continue

        header = _parse_segment_header(line, line_number, raw_line)
        if header is not None and _line_has_no_time_range(line):
            if pending_title is not None:
                warnings.append(ParseWarning(pending_title.line_number, pending_title.raw_line))
            pending_title = None
            block = header
            continue

        candidate = _parse_clip_candidate(line)
        if candidate is not None:
            title = candidate.title
            number = candidate.number
            if block is not None:
                if not title:
                    title = block.title
                number = number or block.number
                block = None
            if pending_title is not None:
                if not title:
                    title = pending_title.title
                    number = number or pending_title.number
                else:
                    warnings.append(ParseWarning(pending_title.line_number, pending_title.raw_line))
                pending_title = None
            clip, next_auto_number = _build_clip(candidate, next_auto_number, number=number, title=title)
            clips.append(clip)
            continue

        start_marker = _parse_begin_marker(line)
        if start_marker is not None:
            if block is None:
                block = _BeginEndBlock(
                    line_number=pending_title.line_number if pending_title else line_number,
                    raw_line=pending_title.raw_line if pending_title else raw_line,
                    number=pending_title.number if pending_title else None,
                    title=pending_title.title if pending_title else "",
                )
                pending_title = None
            block.start, block.start_title = start_marker
            maybe_clip, next_auto_number = _finalize_block_if_ready(block, next_auto_number)
            if maybe_clip is not None:
                clips.append(maybe_clip)
                block = None
            continue

        end_marker = _parse_end_marker(line)
        if end_marker is not None:
            if block is None:
                warnings.append(ParseWarning(line_number, raw_line))
                continue
            block.end, block.end_title = end_marker
            maybe_clip, next_auto_number = _finalize_block_if_ready(block, next_auto_number)
            if maybe_clip is not None:
                clips.append(maybe_clip)
                block = None
            continue

        title_only = _parse_title_only_line(line, line_number, raw_line)
        if title_only is not None and title_only.number is not None:
            if pending_title is not None:
                warnings.append(ParseWarning(pending_title.line_number, pending_title.raw_line))
            pending_title = title_only
            continue

        if clips and pending_title is None:
            clips[-1] = _append_title_continuation(clips[-1], line)
            continue

        if pending_title is not None:
            warnings.append(ParseWarning(pending_title.line_number, pending_title.raw_line))
        pending_title = title_only or _PendingTitle(line_number, raw_line, None, _clean_title(line))

    if pending_title is not None:
        warnings.append(ParseWarning(pending_title.line_number, pending_title.raw_line))
    if block is not None:
        warnings.append(ParseWarning(block.line_number, block.raw_line))

    return ParseResult(clips=clips, warnings=warnings)


def parse_clip_line(raw_line: str) -> ParsedClipLine | None:
    """Parse a single message line, returning None when unsupported."""

    line = _normalize_line(raw_line)
    if not line or _is_note_line(line):
        return None

    candidate = _parse_clip_candidate(line)
    if candidate is None:
        return None

    clip, _ = _build_clip(candidate, next_auto_number=1)
    return clip


def _parse_clip_candidate(line: str) -> _ClipCandidate | None:
    return _parse_csv_like_line(line) or _parse_begin_end_line(line) or _parse_range_line(line)


def _parse_csv_like_line(line: str) -> _ClipCandidate | None:
    parts = [part.strip() for part in re.split(r"[,،]", line) if part.strip()]
    if len(parts) < 4:
        return None

    number = _parse_sequence_number(parts[0])
    title = _clean_title(parts[1])
    start = _try_normalize_timestamp(parts[2])
    end = _try_normalize_timestamp(parts[3])

    if number is None or start is None or end is None or not title:
        return None

    return _ClipCandidate(number=number, title=title, start=start, end=end)


def _parse_begin_end_line(line: str) -> _ClipCandidate | None:
    if "البداية" not in line or "النهاية" not in line:
        return None

    prefix, start_part, end_part = _split_begin_end_line(line)
    if start_part is None or end_part is None:
        return None

    start_marker = _extract_time_and_text(start_part)
    end_marker = _extract_time_and_text(end_part)
    if start_marker is None or end_marker is None:
        return None

    number = _parse_sequence_number(prefix)
    prefix_title = _clean_title(_strip_sequence_prefix(prefix))
    start, start_title = start_marker
    end, end_title = end_marker
    title = prefix_title or start_title or end_title

    return _ClipCandidate(number=number, title=title, start=start, end=end)


def _parse_range_line(line: str) -> _ClipCandidate | None:
    match = _RANGE_PATTERN.search(line)
    if not match:
        return None

    start = _try_normalize_timestamp(match.group(1))
    end = _try_normalize_timestamp(match.group(2))
    if start is None or end is None:
        return None

    prefix = line[: match.start()]
    suffix = line[match.end() :]
    number = _parse_sequence_number(prefix)
    prefix_title = _clean_title(_strip_sequence_prefix(prefix))
    suffix_title = _clean_title(suffix)
    title = prefix_title or suffix_title

    return _ClipCandidate(number=number, title=title, start=start, end=end)


def _parse_title_only_line(line: str, line_number: int, raw_line: str) -> _PendingTitle | None:
    title = _clean_title(_strip_sequence_prefix(line))
    if not title:
        return None

    return _PendingTitle(
        line_number=line_number,
        raw_line=raw_line,
        number=_parse_sequence_number(line),
        title=title,
    )


def _parse_segment_header(line: str, line_number: int, raw_line: str) -> _BeginEndBlock | None:
    if not line.startswith("المقطع"):
        return None

    return _BeginEndBlock(
        line_number=line_number,
        raw_line=raw_line,
        number=_parse_sequence_number(line),
        title=_clean_title(_strip_sequence_prefix(line)),
    )


def _parse_begin_marker(line: str) -> tuple[str, str] | None:
    marker = re.search(r"البداية\s*:?", line)
    if not marker:
        return None

    return _extract_time_and_text(line[marker.end() :])


def _parse_end_marker(line: str) -> tuple[str, str] | None:
    marker = re.search(r"النهاية\s*:?", line)
    if not marker:
        return None

    return _extract_time_and_text(line[marker.end() :])


def _finalize_block_if_ready(
    block: _BeginEndBlock,
    next_auto_number: int,
) -> tuple[ParsedClipLine | None, int]:
    if block.start is None or block.end is None:
        return None, next_auto_number

    candidate = _ClipCandidate(
        number=block.number,
        title=block.title or block.start_title or block.end_title,
        start=block.start,
        end=block.end,
    )
    return _build_clip(candidate, next_auto_number)


def _build_clip(
    candidate: _ClipCandidate,
    next_auto_number: int,
    number: int | None = None,
    title: str | None = None,
) -> tuple[ParsedClipLine, int]:
    clip_number = number or candidate.number or next_auto_number
    normalized_title = _clean_title(title if title is not None else candidate.title)
    if not normalized_title:
        normalized_title = f"مقطع {clip_number:02d}"

    return (
        ParsedClipLine(
            number=clip_number,
            title=normalized_title,
            start=candidate.start,
            end=candidate.end,
        ),
        max(next_auto_number, clip_number + 1),
    )


def _append_title_continuation(clip: ParsedClipLine, continuation: str) -> ParsedClipLine:
    return ParsedClipLine(
        number=clip.number,
        title=_clean_title(f"{clip.title} {continuation}"),
        start=clip.start,
        end=clip.end,
    )


def _split_begin_end_line(line: str) -> tuple[str, str | None, str | None]:
    begin_match = re.search(r"البداية\s*:?", line)
    end_match = re.search(r"النهاية\s*:?", line)
    if begin_match is None or end_match is None or end_match.start() < begin_match.end():
        return line, None, None

    return (
        line[: begin_match.start()],
        line[begin_match.end() : end_match.start()],
        line[end_match.end() :],
    )


def _extract_time_and_text(value: str) -> tuple[str, str] | None:
    match = re.search(_TIME_PATTERN, value)
    if not match:
        return None

    timestamp = _try_normalize_timestamp(match.group(0))
    if timestamp is None:
        return None

    title = _clean_title(f"{value[: match.start()]} {value[match.end() :]}")
    return timestamp, title


def _parse_sequence_number(text: str) -> int | None:
    for word, number in _ARABIC_ORDINALS.items():
        if word in text:
            return number

    match = re.search(r"(?:^|\s)المقطع\s+(\d+)\b", text)
    if match:
        return int(match.group(1))

    match = re.search(r"^\s*(\d+)\b", text)
    if match:
        return int(match.group(1))

    return None


def _strip_sequence_prefix(text: str) -> str:
    text = re.sub(r"^\s*\d+\s*[-–—.)]\s*", "", text)
    text = re.sub(r"^\s*المقطع\s+\d+\s*", "", text)
    for word in _ARABIC_ORDINALS:
        text = re.sub(rf"^\s*المقطع\s+{re.escape(word)}\s*", "", text)
    return text


def _try_normalize_timestamp(value: str) -> str | None:
    try:
        return normalize_timestamp_text(value)
    except ValueError:
        return None


def _normalize_line(raw_line: str) -> str:
    try:
        return normalize_time_symbols(raw_line)
    except ValueError:
        return ""


def _clean_title(value: str) -> str:
    title = normalize_digits(str(value))
    title = _INTERNAL_RANGE_PATTERN.sub("", title)
    title = re.sub(r"\s+", " ", title).strip(" -–—،,")
    if title.startswith("(") and title.endswith(")"):
        title = title[1:-1].strip()
    return title


def _is_note_line(line: str) -> bool:
    stripped = line.strip()
    return any(stripped.startswith(prefix) for prefix in _NOTE_PREFIXES)


def _line_has_no_time_range(line: str) -> bool:
    return _RANGE_PATTERN.search(line) is None
