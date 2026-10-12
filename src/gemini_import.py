"""Import Gemini's YouTube question/answer timing tables without an AI API.

Accepted paste formats are Markdown tables, JSON (including fenced JSON), and
CSV with Arabic or English column names. A rejected or uncertain boundary is
never guessed, silently omitted, or sent to the cutting engine.
"""

from __future__ import annotations

import csv
import io
import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from src.time_utils import format_seconds, normalize_timestamp_text, parse_timestamp


class GeminiImportError(ValueError):
    """The pasted response cannot safely be converted to clip boundaries."""


@dataclass(frozen=True)
class GeminiClip:
    number: int
    title: str
    start: str
    end: str


@dataclass(frozen=True)
class GeminiImportPreview:
    clips: tuple[GeminiClip, ...]
    source_url: str | None
    warnings: tuple[str, ...]


_HEADER_ALIASES = {
    "number": {"number", "id", "#", "م", "رقم", "الرقم", "رقم المقطع", "المقطع"},
    "title": {"title", "question", "عنوان", "عنوان السؤال", "السؤال", "نص السؤال", "اسم المقطع"},
    "start": {"start", "start time", "بداية", "البداية", "وقت البداية", "وقت بدء السؤال", "بداية السؤال", "من"},
    "end": {"end", "end time", "نهاية", "النهاية", "وقت النهاية", "نهاية الجواب", "نهاية الاجابة", "الى"},
    "url": {"url", "link", "video url", "source url", "الرابط", "رابط الفيديو", "رابط", "رابط المقطع"},
}
_REVERSE_HEADERS = {alias: name for name, aliases in _HEADER_ALIASES.items() for alias in aliases}
_URL = re.compile(
    r"https?://(?:www\.)?(?:youtube\.com/(?:watch\?[^\s<>)|]+|live/[^\s<>)|]+|shorts/[^\s<>)|]+)|youtu\.be/[^\s<>)|]+)",
    re.IGNORECASE,
)
_TIME = re.compile(r"(?<!\d)(?:\d{1,3}:)?\d{1,2}:\d{1,2}(?:\.\d{1,3})?(?!\d)")
_SEPARATOR = re.compile(r"^:?-{3,}:?$")


def parse_gemini_response(text: str | None) -> GeminiImportPreview:
    """Parse and validate *all* clip rows before returning any of them.

    Uncertain or missing timestamps block the import. The original local video
    stays authoritative, and this parser never downloads or modifies a video.
    """
    raw = (text or "").strip()
    if not raw:
        raise GeminiImportError("الصق رد Gemini الذي يحتوي على عناوين الأسئلة وأوقات القص.")

    rows: list[dict[str, Any]] | None = None
    source_url: str | None = None
    for candidate in _json_candidates(raw):
        try:
            document = json.loads(candidate)
        except (ValueError, TypeError):
            continue
        if isinstance(document, dict) and isinstance(document.get("clips"), list):
            rows = [_mapping_from_json(item) for item in document["clips"]]
            source_url = _youtube_url(str(document.get("video_url") or document.get("source_url") or ""))
            break
        if isinstance(document, list):
            rows = [_mapping_from_json(item) for item in document]
            break

    if rows is None:
        rows = _markdown_rows(raw)
    if rows is None:
        rows = _csv_rows(raw)
    if rows is None:
        raise GeminiImportError(
            "لم أجد جدولًا صالحًا. اطلب من Gemini جدولًا بأعمدة "
            "م، عنوان السؤال، وقت البداية، وقت النهاية؛ أو JSON يحتوي على clips."
        )
    if not rows:
        raise GeminiImportError("نتيجة Gemini لا تحتوي على أي مقطع.")

    errors: list[str] = []
    clips: list[GeminiClip] = []
    urls: set[str] = set()
    for row_number, row in enumerate(rows, 1):
        try:
            clip = _clip_from_row(row, row_number)
        except (ValueError, TypeError) as error:
            errors.append(f"المقطع {row_number}: {error}")
            continue
        clips.append(clip)
        video_url = _youtube_url(str(row.get("url") or ""))
        if video_url:
            urls.add(_video_identity(video_url))

    if errors:
        raise GeminiImportError("لا يمكن استيراد بعض أوقات Gemini:\n" + "\n".join(errors[:15]))
    numbers = [clip.number for clip in clips]
    if len(set(numbers)) != len(numbers):
        raise GeminiImportError("أرقام المقاطع مكررة. صحح القائمة قبل الاستيراد.")

    raw_links = {_video_identity(url) for url in _URL.findall(raw)}
    if source_url:
        raw_links.add(_video_identity(source_url))
    urls |= raw_links
    if len(urls) > 1:
        raise GeminiImportError("تم العثور على أكثر من فيديو يوتيوب. الصق نتائج فيديو واحد فقط.")
    source_url = next(iter(urls), None)

    warnings: list[str] = []
    chron = sorted(clips, key=lambda item: parse_timestamp(item.start))
    for index, clip in enumerate(chron):
        start = parse_timestamp(clip.start)
        end = parse_timestamp(clip.end)
        if end - start < 8:
            warnings.append(f"المقطع {clip.number} قصير جدًا ({end - start:g} ثوانٍ): راجع اكتمال الجواب.")
        if index:
            prior = chron[index - 1]
            prior_end = parse_timestamp(prior.end)
            if start < prior_end:
                warnings.append(f"المقطعان {prior.number} و{clip.number} متداخلان؛ راجع الحدود.")
            elif start - prior_end > 30:
                warnings.append(
                    f"فجوة {start - prior_end:g} ثانية بين المقطعين {prior.number} و{clip.number}: "
                    "قد تكون استراحة أو سؤالًا مفقودًا."
                )
    return GeminiImportPreview(tuple(clips), source_url, tuple(warnings))


def _json_candidates(text: str) -> list[str]:
    fenced = re.findall(r"```(?:json)?\s*([\s\S]*?)```", text, flags=re.IGNORECASE)
    return [*fenced, text]


def _mapping_from_json(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {"title": "", "start": None, "end": None}
    mapped = _map_headers(item)
    if "number" not in mapped:
        mapped["number"] = item.get("id")
    return mapped


def _markdown_rows(text: str) -> list[dict[str, Any]] | None:
    lines = [line.strip() for line in text.splitlines()]
    for index, line in enumerate(lines):
        if "|" not in line:
            continue
        headings = _split_markdown_cells(line)
        columns = _column_positions(headings)
        if not all(name in columns for name in ("title", "start", "end")):
            continue
        rows: list[dict[str, Any]] = []
        for row_line in lines[index + 1:]:
            if not row_line:
                if rows:
                    break
                continue
            if "|" not in row_line:
                if rows:
                    break
                continue
            values = _split_markdown_cells(row_line)
            if all(_SEPARATOR.fullmatch(cell.replace(" ", "")) for cell in values):
                continue
            if len(values) != len(headings):
                raise GeminiImportError("جدول Gemini غير منتظم: عدد الأعمدة مختلف بين الصفوف.")
            rows.append({name: values[position] for name, position in columns.items()})
        return rows
    return None


def _split_markdown_cells(line: str) -> list[str]:
    value = line.strip().strip("|")
    return [cell.strip() for cell in re.split(r"(?<!\\)\|", value)]


def _csv_rows(text: str) -> list[dict[str, Any]] | None:
    # A chat explanation is not a CSV document; only parse an explicit header.
    plain = re.sub(r"^```(?:csv)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)
    stream = io.StringIO(plain)
    try:
        reader = csv.DictReader(stream)
        if not reader.fieldnames:
            return None
        column_map = _column_positions(reader.fieldnames)
        if not all(name in column_map for name in ("title", "start", "end")):
            return None
        return [
            {name: row.get(reader.fieldnames[position]) for name, position in column_map.items()}
            for row in reader
            if any(str(value or "").strip() for value in row.values())
        ]
    except csv.Error as error:
        raise GeminiImportError(f"تعذر قراءة جدول CSV: {error}") from error


def _column_positions(headings: list[str]) -> dict[str, int]:
    columns = {}
    for position, header in enumerate(headings):
        canonical = _REVERSE_HEADERS.get(_header_name(header))
        if canonical and canonical not in columns:
            columns[canonical] = position
    return columns


def _map_headers(row: dict[str, Any]) -> dict[str, Any]:
    mapped = {}
    for key, value in row.items():
        canonical = _REVERSE_HEADERS.get(_header_name(str(key)))
        if canonical and canonical not in mapped:
            mapped[canonical] = value
    return mapped


def _header_name(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = re.sub(r"[\u064b-\u065f\u0670\u200b-\u200f]", "", value)
    return re.sub(r"\s+", " ", value.replace("*", "").replace("_", "").strip(" :؟")).strip().lower()


def _clip_from_row(row: dict[str, Any], index: int) -> GeminiClip:
    title = str(row.get("title") or "").strip()
    title = re.sub(r"^\*\*(.*?)\*\*$", r"\1", title)
    if not title or title.lower() in {"null", "غير مؤكد", "غير معروف"}:
        raise ValueError("عنوان السؤال مفقود.")

    raw_number = row.get("number")
    if raw_number is None or str(raw_number).strip() == "":
        number = index
    else:
        text = str(raw_number).translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
        match = re.search(r"(\d+)\s*$", text)
        if not match:
            raise ValueError("رقم المقطع غير صالح.")
        number = int(match.group(1))
    if number <= 0:
        raise ValueError("رقم المقطع يجب أن يكون موجبًا.")

    start = _time_value(row.get("start"), "البداية")
    end = _time_value(row.get("end"), "النهاية")
    if parse_timestamp(start) >= parse_timestamp(end):
        raise ValueError("وقت النهاية يجب أن يكون بعد وقت البداية.")
    return GeminiClip(number=number, title=title, start=start, end=end)


def _time_value(value: Any, name: str) -> str:
    if value is None or str(value).strip().lower() in {"", "null", "none", "غير مؤكد", "غير معروف", "n/a"}:
        raise ValueError(f"وقت {name} غير مؤكد أو مفقود.")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if not 0 <= float(value) < float("inf"):
            raise ValueError(f"وقت {name} غير صالح.")
        return format_seconds(value)
    content = str(value).strip()
    markdown_link = re.match(r"^\[([^\]]+)\]\([^)]+\)$", content)
    if markdown_link:
        content = markdown_link.group(1)
    match = _TIME.search(content)
    if not match:
        raise ValueError(f"وقت {name} غير مفهوم: {content[:40]}")
    return normalize_timestamp_text(match.group(0))


def _youtube_url(value: str) -> str | None:
    found = _URL.search(value)
    return found.group(0) if found else None


def _video_identity(url: str) -> str:
    # Two different timestamp links to the same YouTube video are one source.
    id_match = re.search(r"(?:[?&]v=|youtu\.be/|/live/|/shorts/)([\w-]{6,})", url)
    return f"https://www.youtube.com/watch?v={id_match.group(1)}" if id_match else url.split("&t=")[0]
