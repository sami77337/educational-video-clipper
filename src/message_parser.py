"""Parse pasted Arabic clip request messages into table rows."""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.time_utils import parse_timestamp


AR_UNPARSEABLE_LINE = "تعذر فهم السطر"

_TIME_PATTERN = r"\d{1,3}:\d{1,2}(?::\d{1,2})?"
_DIGIT_TRANSLATION = str.maketrans(
    {
        "٠": "0",
        "١": "1",
        "٢": "2",
        "٣": "3",
        "٤": "4",
        "٥": "5",
        "٦": "6",
        "٧": "7",
        "٨": "8",
        "٩": "9",
        "۰": "0",
        "۱": "1",
        "۲": "2",
        "۳": "3",
        "۴": "4",
        "۵": "5",
        "۶": "6",
        "۷": "7",
        "۸": "8",
        "۹": "9",
    }
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


def parse_clip_message(message: str) -> ParseResult:
    """Parse pasted plain text into clips and warnings."""

    clips: list[ParsedClipLine] = []
    warnings: list[ParseWarning] = []

    for line_number, raw_line in enumerate(message.splitlines(), start=1):
        if not raw_line.strip():
            continue

        parsed_line = parse_clip_line(raw_line)
        if parsed_line is None:
            warnings.append(ParseWarning(line_number=line_number, raw_line=raw_line))
        else:
            clips.append(parsed_line)

    return ParseResult(clips=clips, warnings=warnings)


def parse_clip_line(raw_line: str) -> ParsedClipLine | None:
    """Parse a single message line, returning None when unsupported."""

    line = normalize_digits(raw_line).strip()
    if not line:
        return None

    parsers = (
        _parse_csv_like_line,
        _parse_begin_end_line,
        _parse_numbered_time_line,
    )
    for parser in parsers:
        parsed_line = parser(line)
        if parsed_line is not None:
            return parsed_line

    return None


def normalize_digits(text: str) -> str:
    """Convert Arabic-Indic and Persian digits to ASCII digits."""

    return text.translate(_DIGIT_TRANSLATION)


def _parse_csv_like_line(line: str) -> ParsedClipLine | None:
    parts = [part.strip() for part in re.split(r"[,،]", line) if part.strip()]
    if len(parts) < 4:
        return None

    number = _parse_sequence_number(parts[0])
    title = parts[1].strip()
    start = _normalize_timestamp(parts[2])
    end = _normalize_timestamp(parts[3])

    if number is None or start is None or end is None or not title:
        return None

    return ParsedClipLine(number=number, title=title, start=start, end=end)


def _parse_begin_end_line(line: str) -> ParsedClipLine | None:
    pattern = re.compile(
        rf"(?P<prefix>.*?)"
        rf"البداية\s*[:：]?\s*(?P<start>{_TIME_PATTERN})"
        rf"\s*(?P<title>.*?)"
        rf"النهاية\s*[:：]?\s*(?P<end>{_TIME_PATTERN})"
        rf"(?P<tail>.*)$"
    )
    match = pattern.search(line)
    if not match:
        return None

    number = _parse_sequence_number(match.group("prefix"))
    start = _normalize_timestamp(match.group("start"))
    end = _normalize_timestamp(match.group("end"))
    title = _clean_title(match.group("title")) or _clean_title(match.group("tail"))

    if number is None or start is None or end is None or not title:
        return None

    return ParsedClipLine(number=number, title=title, start=start, end=end)


def _parse_numbered_time_line(line: str) -> ParsedClipLine | None:
    pattern = re.compile(
        rf"^\s*(?P<number>\d+)\s*[-–—.)]\s*"
        rf"(?P<start>{_TIME_PATTERN})\s*[-–—]\s*"
        rf"(?P<end>{_TIME_PATTERN})\s*(?P<title>.+?)\s*$"
    )
    match = pattern.match(line)
    if not match:
        return None

    start = _normalize_timestamp(match.group("start"))
    end = _normalize_timestamp(match.group("end"))
    title = _clean_title(match.group("title"))

    if start is None or end is None or not title:
        return None

    return ParsedClipLine(
        number=int(match.group("number")),
        title=title,
        start=start,
        end=end,
    )


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


def _normalize_timestamp(value: str) -> str | None:
    parts = value.strip().split(":")
    if len(parts) not in (2, 3) or not all(part.isdigit() for part in parts):
        return None

    numbers = [int(part) for part in parts]
    if len(numbers) == 2:
        timestamp = f"{numbers[0]:02}:{numbers[1]:02}"
    else:
        timestamp = f"{numbers[0]:02}:{numbers[1]:02}:{numbers[2]:02}"

    try:
        parse_timestamp(timestamp)
    except ValueError:
        return None

    return timestamp


def _clean_title(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" -–—،,")
