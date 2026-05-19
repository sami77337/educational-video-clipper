"""Smart paste parser for real-world Arabic clip request messages.

This parser is intentionally preview-only. It extracts likely video URLs,
project/title text, clip ranges, warnings, and unparsed lines without touching
the current table import, download, or cutting workflows.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.time_utils import parse_timestamp, normalize_digits, normalize_time_symbols, normalize_timestamp_text


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
    "يحتاج قص من الداخل",
    "استثناء",
    "احذف",
    "حذف",
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
_EXCLUSION_CUE_PATTERN = re.compile(r"(?:استثناء|حذف|احذف|يقطع|يحتاج\s+قص\s+من\s+الداخل)\s*:?\s*")
_START_NOTE_PATTERN = re.compile(
    r"(?:اول\s+كلمة|أول\s+كلمة|كلمة\s+البداية|البداية)\s*:?\s*"
    r"(.+?)(?=(?:اخر\s+كلمة|آخر\s+كلمة|كلمة\s+النهاية|النهاية)\s*:?|$)"
)
_END_NOTE_PATTERN = re.compile(
    r"(?:اخر\s+كلمة|آخر\s+كلمة|كلمة\s+النهاية|النهاية)\s*:?\s*(.+)$"
)


@dataclass(frozen=True)
class SmartPasteExclusion:
    """One detected internal exclusion range."""

    start: str
    end: str
    raw_text: str = ""


@dataclass(frozen=True)
class SmartPasteClip:
    """One parsed clip candidate for preview."""

    number: int
    title: str
    start: str
    end: str
    line_number: int
    raw_line: str
    exclusions: list[SmartPasteExclusion] = field(default_factory=list)
    start_note: str = ""
    end_note: str = ""
    general_notes: list[str] = field(default_factory=list)

    @property
    def exclusions_text(self) -> str:
        return ", ".join(f"{exclusion.start}-{exclusion.end}" for exclusion in self.exclusions)

    @property
    def notes_text(self) -> str:
        notes: list[str] = []
        if self.start_note:
            notes.append(f"ملاحظة بداية المقطع: {self.start_note}")
        if self.end_note:
            notes.append(f"ملاحظة نهاية المقطع: {self.end_note}")
        notes.extend(self.general_notes)
        return " | ".join(notes)


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
    exclusions: list[SmartPasteExclusion] = field(default_factory=list)
    invalid_exclusions: list[SmartPasteExclusion] = field(default_factory=list)
    start_note: str = ""
    end_note: str = ""
    general_notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _ClipMetadata:
    title: str = ""
    exclusions: list[SmartPasteExclusion] = field(default_factory=list)
    invalid_exclusions: list[SmartPasteExclusion] = field(default_factory=list)
    start_note: str = ""
    end_note: str = ""
    general_notes: list[str] = field(default_factory=list)


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
            warnings.extend(_validate_candidate_exclusions(candidate, context))
            if candidate.exclusions:
                warnings.append(
                    SmartPasteWarning(
                        context.line_number,
                        f"تم العثور على استثناء داخل المقطع في السطر {context.line_number}",
                        context.raw_line,
                    )
                )
            if candidate.start_note:
                warnings.append(
                    SmartPasteWarning(
                        context.line_number,
                        f"ملاحظة بداية المقطع في السطر {context.line_number}: {candidate.start_note}",
                        context.raw_line,
                    )
                )
            if candidate.end_note:
                warnings.append(
                    SmartPasteWarning(
                        context.line_number,
                        f"ملاحظة نهاية المقطع في السطر {context.line_number}: {candidate.end_note}",
                        context.raw_line,
                    )
                )
            clip_number = len(clips) + 1
            clips.append(
                SmartPasteClip(
                    number=clip_number,
                    title=candidate.title or f"مقطع {clip_number:02d}",
                    start=candidate.start,
                    end=candidate.end,
                    line_number=context.line_number,
                    raw_line=context.raw_line,
                    exclusions=candidate.exclusions,
                    start_note=candidate.start_note,
                    end_note=candidate.end_note,
                    general_notes=candidate.general_notes,
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
    metadata = _extract_clip_metadata(text, start, end, main_match=match)
    prefix_title = _clean_title(_remove_note_markers(prefix))
    suffix_title = _clean_title(_remove_note_markers(suffix))
    title = metadata.title or prefix_title or suffix_title
    return _ClipCandidate(
        title=title,
        start=start,
        end=end,
        exclusions=metadata.exclusions,
        invalid_exclusions=metadata.invalid_exclusions,
        start_note=metadata.start_note,
        end_note=metadata.end_note,
        general_notes=metadata.general_notes,
    )


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
    notes = _extract_notes_from_text(f"{prefix} {start_title} {end_title}")
    title = notes.title or _clean_title(prefix) or _clean_title(start_title) or _clean_title(end_title)
    return _ClipCandidate(
        title=title,
        start=start,
        end=end,
        start_note=notes.start_note,
        end_note=notes.end_note,
        general_notes=notes.general_notes,
    )


def _extract_time_and_remaining_text(text: str) -> tuple[str, str] | None:
    match = re.search(_TIME_PATTERN, text)
    if match is None:
        return None

    timestamp = _normalize_time(match.group(0))
    if timestamp is None:
        return None

    remaining_text = f"{text[: match.start()]} {text[match.end() :]}"
    return timestamp, remaining_text


def _extract_clip_metadata(text: str, clip_start: str, clip_end: str, main_match: re.Match[str]) -> _ClipMetadata:
    exclusion_matches = _find_exclusion_matches(text, main_match)
    exclusions: list[SmartPasteExclusion] = []
    invalid_exclusions: list[SmartPasteExclusion] = []

    for match in exclusion_matches:
        exclusion = _build_exclusion_from_match(match, text)
        if exclusion is None:
            continue
        if _exclusion_has_valid_order(exclusion) and _exclusion_inside_clip(exclusion, clip_start, clip_end):
            exclusions.append(exclusion)
        else:
            invalid_exclusions.append(exclusion)

    cleaned_title_source = _strip_number_prefix(f"{text[: main_match.start()]} {text[main_match.end() :]}")
    cleaned_title_source = _RANGE_PATTERN.sub(" ", cleaned_title_source)
    notes = _extract_notes_from_text(cleaned_title_source)
    cleaned_title_source = _EXCLUSION_CUE_PATTERN.sub(" ", notes.title)

    return _ClipMetadata(
        title=_clean_title(cleaned_title_source),
        exclusions=exclusions,
        invalid_exclusions=invalid_exclusions,
        start_note=notes.start_note,
        end_note=notes.end_note,
        general_notes=notes.general_notes,
    )


def _extract_notes_from_text(text: str) -> _ClipMetadata:
    working_text = str(text)
    start_note = ""
    end_note = ""

    start_match = _START_NOTE_PATTERN.search(working_text)
    if start_match is not None and not re.search(_TIME_PATTERN, start_match.group(1)):
        start_note = _clean_note_text(start_match.group(1))
        working_text = working_text[: start_match.start()] + " " + working_text[start_match.end() :]

    end_match = _END_NOTE_PATTERN.search(working_text)
    if end_match is not None and not re.search(_TIME_PATTERN, end_match.group(1)):
        end_note = _clean_note_text(end_match.group(1))
        working_text = working_text[: end_match.start()] + " " + working_text[end_match.end() :]

    general_notes: list[str] = []
    if "يحتاج قص من الداخل" in working_text:
        general_notes.append("يحتاج قص من الداخل")
        working_text = working_text.replace("يحتاج قص من الداخل", " ")

    return _ClipMetadata(
        title=_clean_title(working_text),
        start_note=start_note,
        end_note=end_note,
        general_notes=general_notes,
    )


def _find_exclusion_matches(text: str, main_match: re.Match[str]) -> list[re.Match[str]]:
    matches: list[re.Match[str]] = []
    for match in _RANGE_PATTERN.finditer(text):
        if match.start() == main_match.start() and match.end() == main_match.end():
            continue
        before = text[max(0, match.start() - 35) : match.start()]
        after = text[match.end() : min(len(text), match.end() + 20)]
        in_parentheses = before.rfind("(") > before.rfind(")") and ")" in after
        has_cue = bool(_EXCLUSION_CUE_PATTERN.search(before))
        if in_parentheses or has_cue:
            matches.append(match)
    return matches


def _build_exclusion_from_match(match: re.Match[str], text: str) -> SmartPasteExclusion | None:
    start = _normalize_time(match.group(1))
    end = _normalize_time(match.group(2))
    if start is None or end is None:
        return None
    raw_text = text[match.start() : match.end()]
    return SmartPasteExclusion(start=start, end=end, raw_text=raw_text)


def _validate_candidate_exclusions(
    candidate: _ClipCandidate,
    context: _LineContext,
) -> list[SmartPasteWarning]:
    warnings: list[SmartPasteWarning] = []
    for exclusion in candidate.invalid_exclusions:
        if not _exclusion_has_valid_order(exclusion):
            warnings.append(
                SmartPasteWarning(
                    context.line_number,
                    "تحذير: وقت الاستثناء غير صحيح",
                    context.raw_line,
                )
            )
        elif not _exclusion_inside_clip(exclusion, candidate.start, candidate.end):
            warnings.append(
                SmartPasteWarning(
                    context.line_number,
                    "تحذير: الاستثناء خارج حدود المقطع",
                    context.raw_line,
                )
            )
    return warnings


def _exclusion_has_valid_order(exclusion: SmartPasteExclusion) -> bool:
    return parse_timestamp(exclusion.start) < parse_timestamp(exclusion.end)


def _exclusion_inside_clip(exclusion: SmartPasteExclusion, clip_start: str, clip_end: str) -> bool:
    clip_start_seconds = parse_timestamp(clip_start)
    clip_end_seconds = parse_timestamp(clip_end)
    exclusion_start_seconds = parse_timestamp(exclusion.start)
    exclusion_end_seconds = parse_timestamp(exclusion.end)
    return clip_start_seconds <= exclusion_start_seconds and exclusion_end_seconds <= clip_end_seconds


def _clean_note_text(value: str) -> str:
    return _clean_title(value)


def _detect_unsupported_patterns(context: _LineContext) -> list[SmartPasteWarning]:
    warnings: list[SmartPasteWarning] = []
    text = context.text

    if _has_plus_joined_ranges(text):
        warnings.append(
            SmartPasteWarning(
                context.line_number,
                f"تحذير في السطر {context.line_number}: هذا المقطع يحتوي على أكثر من جزء ويحتاج دعم الدمج لاحقًا",
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


def _remove_note_markers(text: str) -> str:
    text = _START_NOTE_PATTERN.sub(" ", text)
    text = _END_NOTE_PATTERN.sub(" ", text)
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
