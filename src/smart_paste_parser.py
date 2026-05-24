"""Smart paste parser for real-world Arabic clip request messages.

The parser is intentionally preview-only. It extracts evidence from pasted
messages so the UI can show a safe preview before any URL, title, or clip row
is applied.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace

from src.time_utils import (
    format_seconds,
    normalize_digits,
    normalize_timestamp_text,
    parse_timestamp,
)


VERY_SHORT_CLIP_SECONDS = 3
VERY_LONG_CLIP_SECONDS = 20 * 60

_TIME_PATTERN = r"\d{1,3}\s*:\s*\d{1,2}(?:\s*:\s*\d{1,2})?"
_SHORT_END_TIME_PATTERN = r"\d{1,3}"
_END_TIME_PATTERN = rf"(?:{_TIME_PATTERN}|{_SHORT_END_TIME_PATTERN})"
_RANGE_SEPARATOR_PATTERN = (
    r"(?:[-–—−]|إلى|الى|إلي|الي|حتّى|حتى|و\s*حتى|وحتى|لغاية|to)"
)
_RANGE_PATTERN = re.compile(
    rf"(?:\bfrom\s+|من\s+(?:الدقيقة\s+)?)?"
    rf"[\[(]?\s*({_TIME_PATTERN})\s*[\])]?َ?"
    rf"\s*{_RANGE_SEPARATOR_PATTERN}\s*"
    rf"(?:\bto\s+|الدقيقة\s+)?"
    rf"[\[(]?\s*({_END_TIME_PATTERN})\s*[\])]?َ?",
    re.IGNORECASE,
)
_YOUTUBE_URL_PATTERN = re.compile(
    r"https?://(?:www\.|m\.)?"
    r"(?:youtube\.com/(?:watch\?[^\s<>()\[\]]+|live/[^\s<>()\[\]]+|shorts/[^\s<>()\[\]]+)"
    r"|youtu\.be/[^\s<>()\[\]]+)",
    re.IGNORECASE,
)
_WHATSAPP_METADATA_PATTERN = re.compile(r"^\[\d{1,2}/\d{1,2}/\d{2,4}[^\]]*\]\s*[^:]{1,80}:\s*")
_SINGLE_TIME_PATTERN = re.compile(_TIME_PATTERN)
_PLUS_JOINED_RANGE_PATTERN = re.compile(
    rf"{_TIME_PATTERN}\s*{_RANGE_SEPARATOR_PATTERN}\s*{_TIME_PATTERN}\s*\+\s*"
    rf"{_TIME_PATTERN}\s*{_RANGE_SEPARATOR_PATTERN}\s*{_TIME_PATTERN}",
    re.IGNORECASE,
)
_INTERNAL_RANGE_IN_PARENTHESES_PATTERN = re.compile(
    rf"\(\s*{_TIME_PATTERN}\s*{_RANGE_SEPARATOR_PATTERN}\s*{_TIME_PATTERN}\s*\)",
    re.IGNORECASE,
)

_INTERNAL_CUT_PHRASES = (
    "مابين القوسين يقطع",
    "ما بين القوسين يقطع",
    "مابين القوسين",
    "ما بين القوسين",
    "يحتاج قص من الداخل",
    "يحتاج الفيديو إلى بعض الاقتصاصات في أثنائه",
    "قصوا الاستراحة",
    "الاستراحة",
    "قص داخل المقطع",
    "حذف داخل المقطع",
    "احذف من داخل المقطع",
    "هذا الجزء يقطع",
    "استثناء",
    "احذف",
    "حذف",
    "يقطع",
)
_EXCLUSION_CUE_PATTERN = re.compile(
    r"(?:"
    r"استثناء|استثني|حذف|احذف|يحذف|إزالة|ازالة|شيل|قص|اقتصاص|الاقتصاصات|بدون|"
    r"لا\s+نريد|لا\s+اريد|لا\s+أريد|استبعد|تجاهل|يقطع|قصوا|قصوه|"
    r"لتقصير\s+المقطع|تكون\s+الفائدة\s+افضل|يقصر\s+المقطع|"
    r"skip|exclude|remove|cut\s+out|delete|omit|without|"
    r"مابين\s+القوسين\s+يقطع|ما\s+بين\s+القوسين\s+يقطع|"
    r"يحتاج\s+قص\s+من\s+الداخل|قص\s+داخل\s+المقطع|حذف\s+داخل\s+المقطع|"
    r"احذف\s+من\s+داخل\s+المقطع|قصوا\s+الاستراحة|هذا\s+الجزء\s+يقطع"
    r")\s*:?\s*"
    ,
    re.IGNORECASE,
)
_LOOSE_EXCLUSION_RANGE_PATTERN = re.compile(
    rf"(?:من\s+)?(?:الدقيقة\s+|minute\s+)?"
    rf"({_END_TIME_PATTERN})\s*{_RANGE_SEPARATOR_PATTERN}\s*"
    rf"(?:الدقيقة\s+|minute\s+)?({_END_TIME_PATTERN})",
    re.IGNORECASE,
)
_START_LABEL_PATTERN = re.compile(r"(?:البداية|بداية|بداية\s+المقطع|من\s+البداية)\s*:?")
_END_LABEL_PATTERN = re.compile(r"(?:النهاية|نهاية|نهاية\s+المقطع|إلى\s+النهاية|الى\s+النهاية)\s*:?")
_START_NOTE_PATTERN = re.compile(
    r"(?:اول\s+كلمة|أول\s+كلمة|كلمة\s+البداية|من\s+كلمة)\s*:?\s*"
    r"(.+?)(?=(?:اخر\s+كلمة|آخر\s+كلمة|كلمة\s+النهاية|إلى\s+كلمة|الى\s+كلمة)\s*:?|$)"
)
_END_NOTE_PATTERN = re.compile(
    r"(?:اخر\s+كلمة|آخر\s+كلمة|كلمة\s+النهاية|إلى\s+كلمة|الى\s+كلمة)\s*:?\s*(.+)$"
)
_TEXTUAL_BOUNDARY_PHRASES = (
    "تقريبا",
    "تقريباً",
    "إلى بداية دعاء الشيخ",
    "الى بداية دعاء الشيخ",
    "اول كلمة",
    "أول كلمة",
    "اخر كلمة",
    "آخر كلمة",
    "من كلمة",
    "إلى كلمة",
    "الى كلمة",
)
_NOTE_PREFIX_PATTERN = re.compile(r"^(?:>>>>+|ملاحظة\s*:|تنبيه\s*:|قد\s+تحذف)\s*")


@dataclass(frozen=True)
class SmartPasteExclusion:
    """One detected internal exclusion range."""

    start: str
    end: str
    raw_text: str = ""


@dataclass(frozen=True)
class SmartPastePart:
    """One part of a multi-part clip."""

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
    parts: list[SmartPastePart] = field(default_factory=list)
    start_note: str = ""
    end_note: str = ""
    general_notes: list[str] = field(default_factory=list)
    confidence: str = "high"
    source_lines: dict[str, list[int]] = field(default_factory=dict)

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
        return " | ".join(note for note in notes if note)

    @property
    def multi_part(self) -> bool:
        return len(self.parts) > 1

    @property
    def parts_text(self) -> str:
        if not self.parts:
            return ""
        return " | ".join(
            f"الجزء {index}: {part.start} - {part.end}"
            for index, part in enumerate(self.parts, start=1)
        )


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
class _TitleEvidence:
    title: str
    context: _LineContext


@dataclass
class _LabelBlock:
    title: str = ""
    start: str = ""
    end: str = ""
    start_note: str = ""
    end_note: str = ""
    start_context: _LineContext | None = None
    end_context: _LineContext | None = None
    title_context: _LineContext | None = None
    awaiting: str = ""


@dataclass(frozen=True)
class _ClipCandidate:
    title: str
    start: str
    end: str
    exclusions: list[SmartPasteExclusion] = field(default_factory=list)
    parts: list[SmartPastePart] = field(default_factory=list)
    invalid_exclusions: list[SmartPasteExclusion] = field(default_factory=list)
    start_note: str = ""
    end_note: str = ""
    general_notes: list[str] = field(default_factory=list)
    parser_warnings: list[str] = field(default_factory=list)
    confidence: str = "high"
    source_lines: dict[str, list[int]] = field(default_factory=dict)


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
    url_line_numbers: list[int] = []
    clips: list[SmartPasteClip] = []
    warnings: list[SmartPasteWarning] = []
    unparsed_lines: list[SmartPasteUnparsedLine] = []
    project_title = ""
    project_title_parts: list[_TitleEvidence] = []
    pending_candidate: _ClipCandidate | None = None
    pending_context: _LineContext | None = None
    pending_extra_warnings: list[SmartPasteWarning] = []
    pending_title: _TitleEvidence | None = None
    pending_exclusion_clip_index: int | None = None
    label_block: _LabelBlock | None = None

    contexts = _prepare_contexts(raw_text)

    def add_warning(context: _LineContext, message: str) -> None:
        warnings.append(SmartPasteWarning(context.line_number, message, context.raw_line))

    def set_project_title(evidence: _TitleEvidence) -> None:
        nonlocal project_title, project_title_parts, pending_title
        if not evidence.title:
            return
        if not project_title_parts:
            project_title_parts.append(evidence)
        elif evidence.title not in [part.title for part in project_title_parts]:
            project_title_parts.append(evidence)
        project_title = " - ".join(part.title for part in project_title_parts)
        pending_title = _TitleEvidence(project_title, evidence.context)

    def append_candidate(
        candidate: _ClipCandidate,
        context: _LineContext,
        *,
        title_override: str = "",
        extra_warnings: list[SmartPasteWarning] | None = None,
    ) -> SmartPasteClip | None:
        nonlocal clips, warnings
        if _candidate_has_reversed_time(candidate):
            warnings.append(SmartPasteWarning(context.line_number, "نهاية المقطع قبل بدايته", context.raw_line))
            return None
        title = _clean_title(title_override) if title_override else candidate.title
        if not title:
            title = f"مقطع {len(clips) + 1:02d}"
        if extra_warnings:
            warnings.extend(extra_warnings)
        warnings.extend(_warnings_for_candidate(candidate, context))
        clip = SmartPasteClip(
            number=len(clips) + 1,
            title=title,
            start=candidate.start,
            end=candidate.end,
            line_number=context.line_number,
            raw_line=context.raw_line,
            exclusions=candidate.exclusions,
            parts=candidate.parts,
            start_note=candidate.start_note,
            end_note=candidate.end_note,
            general_notes=candidate.general_notes,
            confidence=candidate.confidence,
            source_lines=candidate.source_lines or _default_source_lines(context.line_number),
        )
        clips.append(clip)
        return clip

    def finalize_pending_candidate(title_override: str = "") -> SmartPasteClip | None:
        nonlocal pending_candidate, pending_context, pending_extra_warnings
        if pending_candidate is None or pending_context is None:
            return None

        clip = append_candidate(
            pending_candidate,
            pending_context,
            title_override=title_override,
            extra_warnings=pending_extra_warnings,
        )
        pending_candidate = None
        pending_context = None
        pending_extra_warnings = []
        return clip

    def clear_pending_title_if_used(source_title: str) -> None:
        nonlocal pending_title
        if pending_title is not None and pending_title.title == source_title:
            pending_title = None

    def handle_following_exclusion_note(context: _LineContext) -> None:
        nonlocal clips, pending_exclusion_clip_index
        if not clips:
            return
        previous_clip = clips[-1]
        exclusions = _extract_following_exclusion_ranges(context.text, previous_clip)
        if not exclusions:
            clips[-1] = replace(
                previous_clip,
                general_notes=[*previous_clip.general_notes, _clean_note_text(context.text)],
            )
            add_warning(context, "ملاحظة تحتاج مراجعة: توجد ملاحظة عن قص داخلي بدون وقت محدد")
            pending_exclusion_clip_index = len(clips) - 1
            return

        attached: list[SmartPasteExclusion] = []
        for exclusion in exclusions:
            if not _exclusion_has_valid_order(exclusion):
                add_warning(context, "نهاية الاستثناء قبل بدايته")
                continue
            if not _exclusion_inside_clip(exclusion, previous_clip.start, previous_clip.end):
                add_warning(context, "وقت الاستثناء خارج حدود المقطع السابق")
                continue
            attached.append(exclusion)
        if not attached:
            return

        updated_exclusions = [*previous_clip.exclusions, *attached]
        clips[-1] = replace(previous_clip, exclusions=updated_exclusions)
        add_warning(context, "استثناء مكتشف من ملاحظة تالية")
        if _exclusions_have_overlap_or_duplicate(updated_exclusions):
            add_warning(context, "يوجد تداخل أو تكرار في الاستثناءات")

    for context in contexts:
        line_urls = _extract_youtube_urls(context.text)
        for url in line_urls:
            if url not in video_urls:
                video_urls.append(url)
                url_line_numbers.append(context.line_number)

        text_without_urls = _remove_urls(context.text).strip()
        if not text_without_urls:
            continue

        context = _LineContext(context.line_number, context.raw_line, text_without_urls)

        if _is_note_line(context.text):
            if clips and _line_has_exclusion_cue(context.text):
                handle_following_exclusion_note(context)
            elif clips:
                previous_clip = clips[-1]
                clips[-1] = replace(
                    previous_clip,
                    general_notes=[*previous_clip.general_notes, _clean_note_text(context.text)],
                )
                add_warning(context, "توجد ملاحظة تحتاج مراجعة يدوية")
            else:
                unparsed_lines.append(SmartPasteUnparsedLine(context.line_number, context.raw_line))
            continue

        unsupported_warnings = _detect_unsupported_patterns(context)

        if clips and _looks_like_following_exclusion_note_line(context.text):
            handle_following_exclusion_note(context)
            continue

        if label_block is not None:
            handled_label = _consume_labeled_context(label_block, context)
            if handled_label:
                if _label_block_is_complete(label_block):
                    candidate = _candidate_from_label_block(label_block, fallback_title=project_title)
                    append_candidate(candidate, label_block.start_context or context)
                    label_block = None
                    pending_title = None
                continue

        if pending_exclusion_clip_index is not None:
            exclusion_candidate = _parse_range_clip(context.text)
            if exclusion_candidate is not None:
                if exclusion_candidate.title:
                    pending_exclusion_clip_index = None
                else:
                    exclusion = SmartPasteExclusion(exclusion_candidate.start, exclusion_candidate.end, context.text)
                    previous_clip = clips[pending_exclusion_clip_index]
                    if _exclusion_has_valid_order(exclusion) and _exclusion_inside_clip(
                        exclusion,
                        previous_clip.start,
                        previous_clip.end,
                    ):
                        clips[pending_exclusion_clip_index] = replace(
                            previous_clip,
                            exclusions=[*previous_clip.exclusions, exclusion],
                        )
                        add_warning(context, "تم اكتشاف وقت قد يكون استثناء داخل المقطع")
                    else:
                        add_warning(context, "تحذير: وقت الاستثناء غير صحيح أو خارج حدود المقطع")
                    pending_exclusion_clip_index = None
                    continue
            else:
                pending_exclusion_clip_index = None

        if _START_LABEL_PATTERN.search(context.text) and _END_LABEL_PATTERN.search(context.text):
            candidate = _parse_begin_end_clip(context.text)
            if candidate is not None:
                finalize_pending_candidate()
                append_candidate(candidate, context, extra_warnings=unsupported_warnings)
                continue

        if _line_has_start_or_end_label(context.text) and not (
            _RANGE_PATTERN.search(context.text) and _has_word_marker_note(context.text)
        ):
            if pending_candidate is not None:
                finalize_pending_candidate()
            if clips and not _line_contains_time(context.text):
                _attach_boundary_note_to_previous_clip(clips, context)
                add_warning(context, "توجد حدود نصية تحتاج مراجعة يدوية")
                continue
            label_block = _start_or_update_label_block(label_block, context, pending_title)
            if _label_block_is_complete(label_block):
                candidate = _candidate_from_label_block(label_block, fallback_title=project_title)
                append_candidate(candidate, label_block.start_context or context)
                label_block = None
                pending_title = None
            continue

        if label_block is not None and _line_contains_time(context.text):
            if _consume_labeled_context(label_block, context):
                if _label_block_is_complete(label_block):
                    candidate = _candidate_from_label_block(label_block, fallback_title=project_title)
                    append_candidate(candidate, label_block.start_context or context)
                    label_block = None
                    pending_title = None
                continue

        candidate = (
            _parse_multi_part_clip(context.text)
            or _parse_begin_end_clip(context.text)
            or _parse_range_clip(context.text)
        )
        if candidate is not None:
            finalize_pending_candidate()
            title_from_previous = ""
            if (
                not candidate.title
                and pending_title is not None
                and (
                    pending_title.title != project_title
                    or _is_clip_title_evidence(pending_title.context.text)
                )
            ):
                title_from_previous = _clean_clip_title_prefix(pending_title.title)
                candidate = replace(
                    candidate,
                    source_lines={
                        **candidate.source_lines,
                        "title": [pending_title.context.line_number],
                    },
                )
            if not candidate.title and not title_from_previous and not candidate.parts:
                pending_candidate = candidate
                pending_context = context
                pending_extra_warnings = list(unsupported_warnings)
                continue
            append_candidate(candidate, context, title_override=title_from_previous, extra_warnings=unsupported_warnings)
            if title_from_previous:
                clear_pending_title_if_used(title_from_previous)
            continue

        if unsupported_warnings:
            finalize_pending_candidate()
            warnings.extend(unsupported_warnings)
            unparsed_lines.append(SmartPasteUnparsedLine(context.line_number, context.raw_line))
            continue

        if pending_candidate is not None:
            if _line_has_exclusion_cue(context.text):
                finalized_clip = finalize_pending_candidate()
                if finalized_clip is not None:
                    pending_exclusion_clip_index = len(clips) - 1
                    add_warning(context, "تم اكتشاف وقت قد يكون استثناء داخل المقطع")
                continue
            if _is_probable_title_line(context.text):
                title = _clean_title(context.text)
                finalize_pending_candidate(title_override=title)
                continue

        if clips and _line_has_exclusion_cue(context.text):
            pending_exclusion_clip_index = len(clips) - 1
            add_warning(context, "تم اكتشاف وقت قد يكون استثناء داخل المقطع")
            continue

        if not clips and _line_has_exclusion_cue(context.text) and _clean_title(context.text):
            pending_title = _TitleEvidence(_clean_title(context.text), context)
            add_warning(context, "تم اكتشاف وقت قد يكون استثناء داخل المقطع")
            continue

        single_time = _extract_single_time(context.text)
        if single_time is not None and label_block is None:
            if pending_title is not None:
                label_block = _LabelBlock(
                    title=pending_title.title,
                    title_context=pending_title.context,
                    start=single_time[0],
                    start_note=_clean_title(single_time[1]),
                    start_context=context,
                    awaiting="start_label",
                )
                continue
            unparsed_lines.append(SmartPasteUnparsedLine(context.line_number, context.raw_line))
            continue

        cleaned_title = _clean_title(context.text)
        if not clips and pending_candidate is None and _looks_like_project_title(context.text):
            evidence = _TitleEvidence(cleaned_title, context)
            if not project_title:
                set_project_title(evidence)
            elif _should_append_project_title_line(context.text, cleaned_title, project_title_parts):
                set_project_title(evidence)
            else:
                pending_title = evidence
            continue

        if _is_probable_title_line(context.text):
            pending_title = _TitleEvidence(cleaned_title, context)
            continue

        unparsed_lines.append(SmartPasteUnparsedLine(context.line_number, context.raw_line))

    finalize_pending_candidate()

    if label_block is not None:
        if label_block.start and not label_block.end:
            warnings.append(
                SmartPasteWarning(
                    (label_block.start_context or label_block.title_context or contexts[-1]).line_number if contexts else 0,
                    "تم العثور على بداية بدون نهاية",
                    (label_block.start_context or label_block.title_context or contexts[-1]).raw_line if contexts else "",
                )
            )
        elif label_block.end and not label_block.start:
            warnings.append(
                SmartPasteWarning(
                    (label_block.end_context or label_block.title_context or contexts[-1]).line_number if contexts else 0,
                    "تم العثور على نهاية بدون بداية",
                    (label_block.end_context or label_block.title_context or contexts[-1]).raw_line if contexts else "",
                )
            )

    if pending_title is not None and pending_title.title != project_title:
        unparsed_lines.append(SmartPasteUnparsedLine(pending_title.context.line_number, pending_title.context.raw_line))

    warnings.extend(_post_parse_warnings(video_urls, url_line_numbers, clips))

    return SmartPastePreview(
        video_urls=video_urls,
        project_title=project_title,
        clips=clips,
        warnings=warnings,
        unparsed_lines=unparsed_lines,
    )


def format_smart_paste_debug_report(preview: SmartPastePreview, original_input: str = "") -> str:
    """Return a text debug report without sensitive cookie/browser data."""

    lines = [
        "تقرير فحص الاستيراد الذكي",
        f"عنوان المشروع: {preview.project_title or 'غير مكتشف'}",
        f"الرابط: {preview.video_urls[0] if preview.video_urls else 'غير مكتشف'}",
        f"عدد المقاطع: {len(preview.clips)}",
        f"عدد التحذيرات: {len(preview.warnings)}",
        f"عدد الأسطر التي تحتاج مراجعة: {len(preview.unparsed_lines)}",
        "",
        "المقاطع:",
    ]
    for clip in preview.clips:
        lines.append(f"{clip.number}. {clip.start} - {clip.end} | {clip.title}")
        if clip.exclusions_text:
            lines.append(f"   الاستثناءات: {clip.exclusions_text}")
        if clip.parts_text:
            lines.append(f"   الأجزاء: {clip.parts_text}")
        if clip.notes_text:
            lines.append(f"   الملاحظات: {clip.notes_text}")
        lines.append(f"   الثقة: {clip.confidence}")
        lines.append(f"   الأسطر: {clip.source_lines}")
    if preview.warnings:
        lines.extend(["", "التحذيرات:"])
        lines.extend(f"- السطر {warning.line_number}: {warning.message_ar}" for warning in preview.warnings)
    if preview.unparsed_lines:
        lines.extend(["", "أسطر تحتاج مراجعة:"])
        lines.extend(f"- السطر {line.line_number}: {line.raw_line}" for line in preview.unparsed_lines)
    if original_input:
        lines.extend(["", "النص الأصلي:", original_input])
    return "\n".join(lines)


def _prepare_contexts(raw_text: str | None) -> list[_LineContext]:
    contexts: list[_LineContext] = []
    for line_number, raw_line in enumerate(str(raw_text or "").splitlines(), start=1):
        context = _prepare_line(raw_line, line_number)
        if context is not None:
            contexts.append(context)
    return contexts


def _prepare_line(raw_line: str, line_number: int) -> _LineContext | None:
    stripped = str(raw_line).strip()
    if not stripped:
        return None
    stripped = _WHATSAPP_METADATA_PATTERN.sub("", stripped).strip()
    if not stripped:
        return None
    normalized = normalize_import_text(stripped)
    return _LineContext(line_number=line_number, raw_line=raw_line, text=normalized)


def normalize_separators(text: str) -> str:
    """Normalize common copied range separators without changing line meaning."""

    normalized = str(text).replace("–", "-").replace("—", "-").replace("−", "-")
    return normalized


def normalize_time_spacing(text: str) -> str:
    """Normalize spaces inside timestamp-like text such as ٣٤: ١٨."""

    return re.sub(r"(?<=\d)\s*:\s*(?=\d)", ":", str(text))


def normalize_import_text(text: str) -> str:
    """Normalize pasted Smart Import text while preserving original line evidence."""

    normalized = normalize_digits(str(text))
    normalized = normalize_separators(normalized)
    normalized = normalize_time_spacing(normalized)
    return normalized


def _extract_youtube_urls(text: str) -> list[str]:
    return [_clean_url(match.group(0)) for match in _YOUTUBE_URL_PATTERN.finditer(text)]


def _remove_urls(text: str) -> str:
    return _YOUTUBE_URL_PATTERN.sub(" ", text)


def _clean_url(url: str) -> str:
    return url.rstrip(".,،؛:)]}؟")


def _parse_multi_part_clip(text: str) -> _ClipCandidate | None:
    if not _has_plus_joined_ranges(text):
        return None
    range_matches = list(_RANGE_PATTERN.finditer(text))
    if len(range_matches) < 2:
        return None
    parts: list[SmartPastePart] = []
    for match in range_matches:
        range_times = _normalize_range_match(match)
        if range_times is not None:
            parts.append(
                SmartPastePart(start=range_times[0], end=range_times[1], raw_text=text[match.start() : match.end()])
            )
    if len(parts) < 2:
        return None
    title_source = _strip_number_prefix(_RANGE_PATTERN.sub(" ", text))
    title_source = re.sub(r"^\s*\+\s*", " ", title_source)
    notes = _extract_notes_from_text(title_source)
    if len(parts) == 2 and _part_gap_is_safe(parts[0], parts[1]):
        exclusion = SmartPasteExclusion(parts[0].end, parts[1].start, raw_text=text)
        return _ClipCandidate(
            title=notes.title,
            start=parts[0].start,
            end=parts[1].end,
            exclusions=[exclusion],
            start_note=notes.start_note,
            end_note=notes.end_note,
            general_notes=notes.general_notes,
            parser_warnings=["تم اكتشاف مقطع مركب مع حذف داخلي"],
            confidence="medium",
        )
    return _ClipCandidate(
        title=notes.title,
        start=parts[0].start,
        end=parts[-1].end,
        parts=parts,
        start_note=notes.start_note,
        end_note=notes.end_note,
        general_notes=notes.general_notes,
        confidence="medium",
    )


def _parse_range_clip(text: str) -> _ClipCandidate | None:
    match = _RANGE_PATTERN.search(text)
    if match is None:
        return None
    range_times = _normalize_range_match(match)
    if range_times is None:
        return None
    start, end, parser_warnings = range_times
    prefix = _strip_number_prefix(text[: match.start()])
    suffix = text[match.end() :]
    metadata = _extract_clip_metadata(text, start, end, main_match=match)
    prefix_title = _clean_title(_remove_note_markers(prefix))
    suffix_title = _clean_title(_remove_note_markers(suffix))
    title = metadata.title or prefix_title or suffix_title
    source_lines = {
        "start": [],
        "end": [],
        "title": [],
        "exclusions": [],
    }
    return _ClipCandidate(
        title=title,
        start=start,
        end=end,
        exclusions=metadata.exclusions,
        invalid_exclusions=metadata.invalid_exclusions,
        start_note=metadata.start_note,
        end_note=metadata.end_note,
        general_notes=metadata.general_notes,
        parser_warnings=parser_warnings,
        confidence="high" if title else "medium",
        source_lines=source_lines,
    )


def _parse_begin_end_clip(text: str) -> _ClipCandidate | None:
    begin_match = _START_LABEL_PATTERN.search(text)
    end_match = _END_LABEL_PATTERN.search(text)
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
    title = notes.title or _clean_title(prefix) or _clean_title(start_title)
    return _ClipCandidate(
        title=title,
        start=start,
        end=end,
        start_note=notes.start_note,
        end_note=notes.end_note,
        general_notes=notes.general_notes,
    )


def _extract_time_and_remaining_text(text: str) -> tuple[str, str] | None:
    match = _SINGLE_TIME_PATTERN.search(text)
    if match is None:
        return None
    timestamp = _normalize_time(match.group(0))
    if timestamp is None:
        return None
    remaining_text = f"{text[: match.start()]} {text[match.end() :]}"
    return timestamp, remaining_text


def _extract_single_time(text: str) -> tuple[str, str] | None:
    matches = list(_SINGLE_TIME_PATTERN.finditer(text))
    if len(matches) != 1 or _RANGE_PATTERN.search(text):
        return None
    match = matches[0]
    timestamp = _normalize_time(match.group(0))
    if timestamp is None:
        return None
    remaining = f"{text[: match.start()]} {text[match.end() :]}"
    return timestamp, _clean_title(remaining)


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
    if start_match is not None and not _line_contains_time(start_match.group(1)):
        start_note = _clean_note_text(start_match.group(1))
        working_text = working_text[: start_match.start()] + " " + working_text[start_match.end() :]
    end_match = _END_NOTE_PATTERN.search(working_text)
    if end_match is not None and not _line_contains_time(end_match.group(1)):
        end_note = _clean_note_text(end_match.group(1))
        working_text = working_text[: end_match.start()] + " " + working_text[end_match.end() :]
    general_notes: list[str] = []
    for phrase in _TEXTUAL_BOUNDARY_PHRASES:
        if phrase in working_text:
            general_notes.append("توجد حدود نصية تحتاج مراجعة يدوية")
            break
    if "يحتاج قص من الداخل" in working_text:
        general_notes.append("يحتاج قص من الداخل")
        working_text = working_text.replace("يحتاج قص من الداخل", " ")
    note_match = re.search(r">>>>+|قد\s+تحذف|ملاحظة\s*:|تنبيه\s*:", working_text)
    if note_match:
        general_notes.append(_clean_note_text(working_text[note_match.start() :]))
        working_text = working_text[: note_match.start()]
    return _ClipMetadata(
        title=_clean_title(working_text),
        start_note=start_note,
        end_note=end_note,
        general_notes=_dedupe(general_notes),
    )


def _find_exclusion_matches(text: str, main_match: re.Match[str]) -> list[re.Match[str]]:
    matches: list[re.Match[str]] = []
    for match in _RANGE_PATTERN.finditer(text):
        if match.start() == main_match.start() and match.end() == main_match.end():
            continue
        before = text[max(0, match.start() - 80) : match.start()]
        after = text[match.end() : min(len(text), match.end() + 30)]
        raw_match = match.group(0).strip()
        in_parentheses = (
            (raw_match.startswith("(") and raw_match.endswith(")"))
            or (raw_match.startswith("(") and ")" in after)
            or (before.rfind("(") > before.rfind(")") and ")" in after)
            or (text[: match.start()].rstrip().endswith("(") and text[match.end() :].lstrip().startswith(")"))
        )
        has_cue = bool(_EXCLUSION_CUE_PATTERN.search(before))
        if in_parentheses or has_cue:
            matches.append(match)
    return matches


def _build_exclusion_from_match(match: re.Match[str], text: str) -> SmartPasteExclusion | None:
    range_times = _normalize_range_match(match)
    if range_times is None:
        return None
    start, end, _parser_warnings = range_times
    return SmartPasteExclusion(start=start, end=end, raw_text=text[match.start() : match.end()])


def _line_has_start_or_end_label(text: str) -> bool:
    return bool(_START_LABEL_PATTERN.search(text) or _END_LABEL_PATTERN.search(text))


def _has_word_marker_note(text: str) -> bool:
    return bool(
        re.search(
            r"(?:اول\s+كلمة|أول\s+كلمة|اخر\s+كلمة|آخر\s+كلمة|كلمة\s+البداية|كلمة\s+النهاية)",
            text,
        )
    )


def _start_or_update_label_block(
    label_block: _LabelBlock | None,
    context: _LineContext,
    pending_title: _TitleEvidence | None,
) -> _LabelBlock:
    block = label_block or _LabelBlock()
    if pending_title is not None and not block.title:
        block.title = pending_title.title
        block.title_context = pending_title.context
    return _consume_label_line(block, context)


def _consume_labeled_context(block: _LabelBlock, context: _LineContext) -> bool:
    if _line_has_start_or_end_label(context.text):
        _consume_label_line(block, context)
        return True
    marker = _extract_single_time(context.text)
    if marker is None:
        return False
    timestamp, remaining = marker
    if block.awaiting == "start":
        block.start = timestamp
        if remaining and not block.start_note:
            block.start_note = remaining
        block.start_context = context
        block.awaiting = ""
        return True
    if block.awaiting == "end":
        block.end = timestamp
        if remaining and not block.end_note:
            block.end_note = remaining
        block.end_context = context
        block.awaiting = ""
        return True
    if block.awaiting == "start_label" and _line_has_start_or_end_label(context.text):
        return True
    return False


def _consume_label_line(block: _LabelBlock, context: _LineContext) -> _LabelBlock:
    start_match = _START_LABEL_PATTERN.search(context.text)
    end_match = _END_LABEL_PATTERN.search(context.text)
    if start_match is not None and (end_match is None or start_match.start() <= end_match.start()):
        segment = context.text[start_match.end() :]
        marker = _extract_time_and_remaining_text(segment)
        if marker is not None:
            block.start, remaining = marker
            if remaining and not block.start_note:
                block.start_note = _clean_title(remaining)
            block.start_context = context
            if not block.title and block.start_note:
                block.title = block.start_note
                block.title_context = context
        else:
            note = _clean_title(segment)
            if note and not block.start_note:
                block.start_note = note
            if block.start and not block.start_context:
                block.start_context = context
            if not block.start:
                block.awaiting = "start"
        return block
    if end_match is not None:
        segment = context.text[end_match.end() :]
        before_label = context.text[: end_match.start()]
        marker = _extract_time_and_remaining_text(f"{before_label} {segment}")
        if marker is not None:
            block.end, remaining = marker
            if segment and not block.end_note:
                without_time = _SINGLE_TIME_PATTERN.sub(" ", segment, count=1)
                block.end_note = _clean_title(without_time)
            elif remaining and not block.end_note:
                block.end_note = _clean_title(remaining)
            block.end_context = context
        else:
            note = _clean_title(segment)
            if note and not block.end_note:
                block.end_note = note
            block.awaiting = "end"
        return block
    return block


def _label_block_is_complete(block: _LabelBlock | None) -> bool:
    return bool(block and block.start and block.end)


def _candidate_from_label_block(block: _LabelBlock, fallback_title: str = "") -> _ClipCandidate:
    original_title = block.title
    title = original_title or block.start_note or fallback_title
    if block.start_note and title.startswith("المقطع"):
        title = block.start_note
    if not original_title and block.start_note and title == block.start_note and fallback_title:
        title = fallback_title
    if block.title_context is not None and _is_clip_title_evidence(block.title_context.text):
        title = _clean_clip_title_prefix(title)
    context_line = (block.start_context or block.end_context or block.title_context)
    line_number = context_line.line_number if context_line else 0
    return _ClipCandidate(
        title=_clean_title(title),
        start=block.start,
        end=block.end,
        start_note="" if _clean_title(title) == block.start_note else block.start_note,
        end_note=block.end_note,
        confidence="high" if title else "medium",
        source_lines={
            "title": [block.title_context.line_number] if block.title_context else [],
            "start": [block.start_context.line_number] if block.start_context else [],
            "end": [block.end_context.line_number] if block.end_context else [],
            "exclusions": [],
            "line": [line_number] if line_number else [],
        },
    )


def _attach_boundary_note_to_previous_clip(clips: list[SmartPasteClip], context: _LineContext) -> None:
    if not clips:
        return
    previous = clips[-1]
    start_match = _START_LABEL_PATTERN.search(context.text)
    end_match = _END_LABEL_PATTERN.search(context.text)
    if start_match:
        note = _clean_note_text(context.text[start_match.end() :])
        clips[-1] = replace(previous, start_note=previous.start_note or note)
    elif end_match:
        note = _clean_note_text(context.text[end_match.end() :])
        clips[-1] = replace(previous, end_note=previous.end_note or note)


def _warnings_for_candidate(candidate: _ClipCandidate, context: _LineContext) -> list[SmartPasteWarning]:
    warnings: list[SmartPasteWarning] = []
    warnings.extend(SmartPasteWarning(context.line_number, message, context.raw_line) for message in candidate.parser_warnings)
    warnings.extend(_validate_candidate_exclusions(candidate, context))
    warnings.extend(_validate_candidate_parts(candidate, context))
    start_seconds = parse_timestamp(candidate.start)
    end_seconds = parse_timestamp(candidate.end)
    if end_seconds <= start_seconds:
        warnings.append(SmartPasteWarning(context.line_number, "نهاية المقطع قبل بدايته", context.raw_line))
    if 0 < end_seconds - start_seconds < VERY_SHORT_CLIP_SECONDS:
        warnings.append(SmartPasteWarning(context.line_number, "هذا المقطع قصير جدًا ويحتاج مراجعة قبل الاعتماد", context.raw_line))
    if end_seconds - start_seconds > VERY_LONG_CLIP_SECONDS:
        warnings.append(SmartPasteWarning(context.line_number, "هذا المقطع طويل جدًا ويحتاج مراجعة قبل الاعتماد", context.raw_line))
    if candidate.confidence == "low":
        warnings.append(SmartPasteWarning(context.line_number, "هذا المقطع يحتاج مراجعة قبل الاعتماد", context.raw_line))
    if candidate.parts:
        warnings.append(SmartPasteWarning(context.line_number, "تم العثور على مقطع مركب من أكثر من جزء", context.raw_line))
        warnings.append(SmartPasteWarning(context.line_number, "تم اكتشاف مقطع متعدد الأجزاء، قد يحتاج مراجعة قبل القص", context.raw_line))
        warnings.append(SmartPasteWarning(context.line_number, "هذا المقطع يحتوي على أكثر من جزء. سيتم دعمه في القص لاحقًا.", context.raw_line))
    if candidate.exclusions:
        warnings.append(SmartPasteWarning(context.line_number, f"تم العثور على استثناء داخل المقطع في السطر {context.line_number}", context.raw_line))
    if candidate.start_note:
        warnings.append(SmartPasteWarning(context.line_number, f"ملاحظة بداية المقطع في السطر {context.line_number}: {candidate.start_note}", context.raw_line))
    if candidate.end_note:
        warnings.append(SmartPasteWarning(context.line_number, f"ملاحظة نهاية المقطع في السطر {context.line_number}: {candidate.end_note}", context.raw_line))
    if "توجد حدود نصية تحتاج مراجعة يدوية" in candidate.general_notes:
        warnings.append(SmartPasteWarning(context.line_number, "توجد حدود نصية تحتاج مراجعة يدوية", context.raw_line))
    for note in candidate.general_notes:
        if note and note not in {"توجد حدود نصية تحتاج مراجعة يدوية", "يحتاج قص من الداخل"}:
            warnings.append(SmartPasteWarning(context.line_number, "توجد ملاحظة تحتاج مراجعة يدوية", context.raw_line))
            break
    return warnings


def _validate_candidate_exclusions(candidate: _ClipCandidate, context: _LineContext) -> list[SmartPasteWarning]:
    warnings: list[SmartPasteWarning] = []
    for exclusion in candidate.invalid_exclusions:
        if not _exclusion_has_valid_order(exclusion):
            warnings.append(SmartPasteWarning(context.line_number, "تحذير: وقت الاستثناء غير صحيح", context.raw_line))
        elif not _exclusion_inside_clip(exclusion, candidate.start, candidate.end):
            warnings.append(SmartPasteWarning(context.line_number, "تحذير: الاستثناء خارج حدود المقطع", context.raw_line))
    return warnings


def _validate_candidate_parts(candidate: _ClipCandidate, context: _LineContext) -> list[SmartPasteWarning]:
    if len(candidate.parts) <= 1:
        return []
    warnings: list[SmartPasteWarning] = []
    seconds_ranges: list[tuple[int, int]] = []
    for part in candidate.parts:
        start_seconds = parse_timestamp(part.start)
        end_seconds = parse_timestamp(part.end)
        seconds_ranges.append((start_seconds, end_seconds))
        if start_seconds >= end_seconds:
            warnings.append(SmartPasteWarning(context.line_number, "تحذير: أحد أجزاء المقطع المركب غير صحيح", context.raw_line))
            break
    if any(seconds_ranges[index][0] < seconds_ranges[index - 1][0] for index in range(1, len(seconds_ranges))):
        warnings.append(SmartPasteWarning(context.line_number, "تحذير: أجزاء المقطع المركب غير مرتبة", context.raw_line))
    for index, current_range in enumerate(seconds_ranges[:-1]):
        next_range = seconds_ranges[index + 1]
        if current_range[1] > next_range[0]:
            warnings.append(SmartPasteWarning(context.line_number, "تحذير: يوجد تداخل بين أجزاء المقطع المركب", context.raw_line))
            break
    return warnings


def _post_parse_warnings(video_urls: list[str], url_line_numbers: list[int], clips: list[SmartPasteClip]) -> list[SmartPasteWarning]:
    warnings: list[SmartPasteWarning] = []
    if len(video_urls) > 1:
        line_number = url_line_numbers[1] if len(url_line_numbers) > 1 else 0
        warnings.append(
            SmartPasteWarning(
                line_number,
                "تم العثور على أكثر من رابط، سيتم استخدام الرابط الأول في هذه النسخة",
                video_urls[1] if len(video_urls) > 1 else "",
            )
        )
        warnings.append(
            SmartPasteWarning(
                line_number,
                "تم العثور على أكثر من رابط، راجع توزيع المقاطع على الروابط",
                video_urls[1] if len(video_urls) > 1 else "",
            )
        )
    seen_ranges: dict[tuple[str, str], SmartPasteClip] = {}
    sorted_clips = sorted(clips, key=lambda clip: (parse_timestamp(clip.start), parse_timestamp(clip.end)))
    for clip in clips:
        key = (clip.start, clip.end)
        if key in seen_ranges:
            warnings.append(SmartPasteWarning(clip.line_number, "يوجد مقطع مكرر بنفس الوقت", clip.raw_line))
        seen_ranges[key] = clip
    for previous, current in zip(sorted_clips, sorted_clips[1:]):
        if parse_timestamp(previous.end) > parse_timestamp(current.start):
            warnings.append(SmartPasteWarning(current.line_number, "يوجد تداخل بين المقاطع", current.raw_line))
    return warnings


def _exclusion_has_valid_order(exclusion: SmartPasteExclusion) -> bool:
    return parse_timestamp(exclusion.start) < parse_timestamp(exclusion.end)


def _exclusion_inside_clip(exclusion: SmartPasteExclusion, clip_start: str, clip_end: str) -> bool:
    clip_start_seconds = parse_timestamp(clip_start)
    clip_end_seconds = parse_timestamp(clip_end)
    exclusion_start_seconds = parse_timestamp(exclusion.start)
    exclusion_end_seconds = parse_timestamp(exclusion.end)
    return clip_start_seconds <= exclusion_start_seconds and exclusion_end_seconds <= clip_end_seconds


def _looks_like_following_exclusion_note_line(text: str) -> bool:
    if not _line_has_exclusion_cue(text):
        return False
    if _is_clip_title_evidence(text):
        return False
    stripped = str(text).strip()
    if stripped.startswith(("-", "–", "—", "*", "•")):
        return True
    if _RANGE_PATTERN.match(stripped):
        return False
    return True


def _extract_following_exclusion_ranges(text: str, previous_clip: SmartPasteClip) -> list[SmartPasteExclusion]:
    ranges: list[SmartPasteExclusion] = []
    seen_spans: list[tuple[int, int]] = []
    for match in _RANGE_PATTERN.finditer(text):
        exclusion = _build_exclusion_from_contextual_match(match, text, previous_clip)
        if exclusion is not None:
            ranges.append(exclusion)
            seen_spans.append(match.span())

    for match in _LOOSE_EXCLUSION_RANGE_PATTERN.finditer(text):
        if any(_spans_overlap(match.span(), span) for span in seen_spans):
            continue
        exclusion = _build_exclusion_from_contextual_match(match, text, previous_clip)
        if exclusion is not None:
            ranges.append(exclusion)
    return ranges


def _build_exclusion_from_contextual_match(
    match: re.Match[str],
    text: str,
    previous_clip: SmartPasteClip,
) -> SmartPasteExclusion | None:
    start = _normalize_exclusion_time_token(match.group(1), previous_clip)
    end = _normalize_exclusion_time_token(match.group(2), previous_clip)
    if start is None or end is None:
        return None
    return SmartPasteExclusion(start=start, end=end, raw_text=text[match.start() : match.end()])


def _normalize_exclusion_time_token(token: str, previous_clip: SmartPasteClip) -> str | None:
    normalized = normalize_digits(str(token)).strip()
    if ":" in normalized:
        timestamp = _normalize_time(normalized)
        if timestamp is None:
            return None
        if parse_timestamp(timestamp) < parse_timestamp(previous_clip.start) and normalized.count(":") == 1:
            shifted = format_seconds(parse_timestamp(timestamp) + 3600)
            if parse_timestamp(shifted) <= parse_timestamp(previous_clip.end):
                return shifted
        return timestamp
    if not normalized.isdigit():
        return None
    minute = int(normalized)
    if minute > 59:
        return None
    clip_start_seconds = parse_timestamp(previous_clip.start)
    clip_end_seconds = parse_timestamp(previous_clip.end)
    base_hour = clip_start_seconds // 3600
    candidate_seconds = base_hour * 3600 + minute * 60
    if candidate_seconds < clip_start_seconds and candidate_seconds + 3600 <= clip_end_seconds:
        candidate_seconds += 3600
    return format_seconds(candidate_seconds)


def _spans_overlap(first: tuple[int, int], second: tuple[int, int]) -> bool:
    return first[0] < second[1] and second[0] < first[1]


def _exclusions_have_overlap_or_duplicate(exclusions: list[SmartPasteExclusion]) -> bool:
    ranges = sorted((parse_timestamp(exclusion.start), parse_timestamp(exclusion.end)) for exclusion in exclusions)
    for previous, current in zip(ranges, ranges[1:]):
        if current[0] <= previous[1]:
            return True
    return False


def _part_gap_is_safe(first: SmartPastePart, second: SmartPastePart) -> bool:
    first_start = parse_timestamp(first.start)
    first_end = parse_timestamp(first.end)
    second_start = parse_timestamp(second.start)
    second_end = parse_timestamp(second.end)
    return first_start < first_end < second_start < second_end


def _detect_unsupported_patterns(context: _LineContext) -> list[SmartPasteWarning]:
    warnings: list[SmartPasteWarning] = []
    if any(phrase in context.text for phrase in _TEXTUAL_BOUNDARY_PHRASES):
        warnings.append(SmartPasteWarning(context.line_number, "توجد حدود نصية تحتاج مراجعة يدوية", context.raw_line))
    if _has_plus_joined_ranges(context.text) and "مقطع واحد" in context.text:
        warnings.append(SmartPasteWarning(context.line_number, "تم اكتشاف مقطع متعدد الأجزاء، قد يحتاج مراجعة قبل القص", context.raw_line))
    return warnings


def _line_has_exclusion_cue(text: str) -> bool:
    return bool(_EXCLUSION_CUE_PATTERN.search(text))


def _has_plus_joined_ranges(text: str) -> bool:
    return _PLUS_JOINED_RANGE_PATTERN.search(text) is not None


def _line_contains_time(text: str) -> bool:
    return _SINGLE_TIME_PATTERN.search(text) is not None


def _line_has_ambiguous_number(text: str) -> bool:
    if _line_contains_time(text):
        return False
    return bool(re.search(r"(?<!\d)\d{1,3}(?!\d)", normalize_digits(text)))


def _candidate_has_reversed_time(candidate: _ClipCandidate) -> bool:
    try:
        return parse_timestamp(candidate.end) <= parse_timestamp(candidate.start)
    except ValueError:
        return False


def _is_note_line(text: str) -> bool:
    stripped = text.strip()
    return stripped.startswith("*") or stripped.startswith(("ملاحظة", "تنبيه", ">>>>", "قد تحذف"))


def _is_probable_title_line(text: str) -> bool:
    if not _clean_title(text):
        return False
    if _extract_youtube_urls(text) or _RANGE_PATTERN.search(text) or _line_contains_time(text):
        return False
    if _line_has_exclusion_cue(text):
        return False
    return True


def _normalize_time(value: str) -> str | None:
    try:
        return normalize_timestamp_text(value)
    except ValueError:
        return None


def _normalize_range_match(match: re.Match[str]) -> tuple[str, str, list[str]] | None:
    start = _normalize_time(match.group(1))
    if start is None:
        return None
    end_text = match.group(2)
    parser_warnings: list[str] = []
    if ":" not in end_text:
        end = _normalize_short_end_time(start, end_text)
        if end is None:
            return None
        parser_warnings.append("وقت النهاية مختصر وتم تفسيره كدقيقة كاملة")
        return start, end, parser_warnings
    end = _normalize_time(end_text)
    if end is None:
        return None
    return start, end, parser_warnings


def _normalize_short_end_time(start: str, end_text: str) -> str | None:
    normalized = normalize_digits(str(end_text)).strip()
    if not normalized.isdigit():
        return None
    end_minute = int(normalized)
    if end_minute > 59:
        return None
    start_seconds = parse_timestamp(start)
    start_hour = start_seconds // 3600
    return format_seconds(start_hour * 3600 + end_minute * 60)


def _strip_number_prefix(text: str) -> str:
    text = normalize_digits(str(text))
    text = re.sub(r"^\s*\d+\s*[-–—.)]\s*", "", text)
    text = re.sub(
        r"^\s*المقطع\s+(?:الأول|الاول|الثاني|الثالث|الرابع|الخامس|السادس|السابع|الثامن|التاسع|العاشر|\d+)\s*[:：-]\s*",
        "",
        text,
    )
    return text


def _strip_title_label_prefix(text: str) -> str:
    text = _strip_number_prefix(text)
    text = re.sub(r"^\s*(?:فائدة|ريلز)\s*[:：]\s*", "", text)
    text = re.sub(r"^\s*عنوان\s+المقطع\s*[:：]\s*", "", text)
    return text


def _remove_note_markers(text: str) -> str:
    text = _START_NOTE_PATTERN.sub(" ", text)
    text = _END_NOTE_PATTERN.sub(" ", text)
    return text


def _clean_title(value: str) -> str:
    title = normalize_digits(str(value))
    title = _YOUTUBE_URL_PATTERN.sub(" ", title)
    title = _INTERNAL_RANGE_IN_PARENTHESES_PATTERN.sub(" ", title)
    title = _strip_title_label_prefix(title)
    title = _NOTE_PREFIX_PATTERN.sub(" ", title)
    for phrase in _INTERNAL_CUT_PHRASES:
        title = title.replace(phrase, " ")
    title = re.sub(r"\(\s*\)", " ", title)
    title = re.sub(r"\s+", " ", title).strip(" :：-–—,،؛[]|")
    leading_parenthesized = re.match(r"^\(([^()]+)\)\s*[\s()،,؛:：-]*$", title)
    if leading_parenthesized is not None:
        title = leading_parenthesized.group(1).strip()
    if title.startswith("(") and title.endswith(")") and _balanced_outer_parentheses(title):
        title = title[1:-1].strip()
    title = re.sub(r"^\(([^()]+)\)\s*([,،])", r"\1 \2", title).strip()
    return title


def _clean_clip_title_prefix(value: str) -> str:
    title = _clean_title(value)
    title = re.sub(r"^\s*مقطع\s+", "", title)
    title = re.sub(r"^\s*(?:فائدة|ريلز|عنوان)\s*[:：]\s*", "", title)
    return title.strip()


def _clean_note_text(value: str) -> str:
    return _clean_title(value)


def _balanced_outer_parentheses(text: str) -> bool:
    depth = 0
    for index, char in enumerate(text):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0 and index != len(text) - 1:
                return False
    return text.startswith("(") and text.endswith(")") and depth == 0


def _looks_like_project_title(text: str) -> bool:
    if _RANGE_PATTERN.search(text) or _line_contains_time(text):
        return False
    if _extract_youtube_urls(text):
        return False
    cleaned = _clean_title(text)
    return bool(cleaned) and len(cleaned) >= 3


def _should_append_project_title_line(
    text: str,
    cleaned_title: str,
    project_title_parts: list[_TitleEvidence],
) -> bool:
    if not project_title_parts or not cleaned_title:
        return False
    if len(project_title_parts) >= 2:
        return False
    if _is_clip_title_evidence(text):
        return False
    stripped = str(text).strip()
    return stripped.startswith("(") or "المجلس" in stripped


def _is_clip_title_evidence(text: str) -> bool:
    stripped_number = _strip_number_prefix(str(text))
    cleaned = _clean_title(stripped_number)
    if not cleaned:
        return False
    return bool(
        re.match(r"^\s*(?:مقطع|فائدة|عنوان(?:\s+المقطع)?|ريلز)\b", stripped_number)
        or stripped_number != str(text)
    )


def _default_source_lines(line_number: int) -> dict[str, list[int]]:
    return {"line": [line_number], "title": [], "start": [line_number], "end": [line_number], "exclusions": []}


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result
