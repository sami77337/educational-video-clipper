"""Helpers for optional export quality and resolution controls."""

from __future__ import annotations

from dataclasses import dataclass


DEFAULT_EXPORT_QUALITY_ENABLED = False
DEFAULT_EXPORT_QUALITY_PRESET = "default"
DEFAULT_ENABLED_QUALITY_PRESET = "balanced"
DEFAULT_RESOLUTION_LIMIT = "original"

AR_EXPORT_QUALITY_APPLIED = "تم تطبيق إعدادات جودة التصدير"
AR_INVALID_EXPORT_QUALITY = "قيمة إعداد جودة التصدير غير صحيحة"

QUALITY_PRESET_LABELS_AR = {
    "default": "الافتراضية",
    "high": "جودة عالية",
    "balanced": "متوازن",
    "small": "حجم أصغر",
}
RESOLUTION_LIMIT_LABELS_AR = {
    "original": "الأصلية",
    "1080p": "1080p",
    "720p": "720p",
}

QUALITY_ENCODING_OPTIONS = {
    "high": {"preset": "slow", "crf": "18"},
    "balanced": {"preset": "medium", "crf": "22"},
    "small": {"preset": "veryfast", "crf": "26"},
}
RESOLUTION_LIMIT_HEIGHTS = {
    "1080p": 1080,
    "720p": 720,
}


class ExportQualityError(ValueError):
    """Raised when export quality settings are invalid."""


@dataclass(frozen=True)
class ExportQualitySettings:
    """Optional encoding quality settings for exported clips."""

    enabled: bool = DEFAULT_EXPORT_QUALITY_ENABLED
    quality_preset: str = DEFAULT_EXPORT_QUALITY_PRESET
    resolution_limit: str = DEFAULT_RESOLUTION_LIMIT


def normalize_export_quality_settings(
    enabled: bool = DEFAULT_EXPORT_QUALITY_ENABLED,
    quality_preset: str | None = DEFAULT_EXPORT_QUALITY_PRESET,
    resolution_limit: str | None = DEFAULT_RESOLUTION_LIMIT,
) -> ExportQualitySettings:
    """Normalize optional export quality settings while preserving safe defaults."""

    if not enabled:
        return ExportQualitySettings()
    return ExportQualitySettings(
        enabled=True,
        quality_preset=normalize_quality_preset(quality_preset or DEFAULT_ENABLED_QUALITY_PRESET),
        resolution_limit=normalize_resolution_limit(resolution_limit),
    )


def normalize_quality_preset(value: str | None) -> str:
    """Return one of the supported custom quality presets."""

    preset = str(value or "").strip().lower()
    aliases = {
        "جودة عالية": "high",
        "متوازن": "balanced",
        "حجم أصغر": "small",
        "smaller": "small",
        "small_size": "small",
    }
    preset = aliases.get(preset, preset)
    if preset in QUALITY_ENCODING_OPTIONS:
        return preset
    raise ExportQualityError(AR_INVALID_EXPORT_QUALITY)


def normalize_resolution_limit(value: str | None) -> str:
    """Return one of the supported resolution limits."""

    resolution = str(value or DEFAULT_RESOLUTION_LIMIT).strip().lower()
    aliases = {
        "الأصلية": "original",
        "original": "original",
        "source": "original",
        "1080": "1080p",
        "720": "720p",
    }
    resolution = aliases.get(resolution, resolution)
    if resolution in RESOLUTION_LIMIT_LABELS_AR:
        return resolution
    raise ExportQualityError(AR_INVALID_EXPORT_QUALITY)


def quality_preset_label_ar(value: str | None) -> str:
    """Return an Arabic label for a normalized quality preset."""

    if value == DEFAULT_EXPORT_QUALITY_PRESET:
        return QUALITY_PRESET_LABELS_AR[DEFAULT_EXPORT_QUALITY_PRESET]
    return QUALITY_PRESET_LABELS_AR[normalize_quality_preset(value)]


def resolution_limit_label_ar(value: str | None) -> str:
    """Return an Arabic label for a normalized resolution limit."""

    return RESOLUTION_LIMIT_LABELS_AR[normalize_resolution_limit(value)]


def export_quality_encoding_arguments(
    export_quality: ExportQualitySettings,
    output_video_path: str,
    *,
    audio_copy: bool = False,
) -> list[str]:
    """Build FFmpeg encoding arguments for default or custom export quality."""

    if export_quality.enabled:
        options = QUALITY_ENCODING_OPTIONS[export_quality.quality_preset]
        args = [
            "-c:v",
            "libx264",
            "-preset",
            options["preset"],
            "-crf",
            options["crf"],
        ]
    else:
        args = [
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
        ]

    if audio_copy:
        args.extend(["-c:a", "copy"])
    else:
        args.extend(["-c:a", "aac", "-b:a", "128k"])
    args.append(str(output_video_path))
    return args


def build_resolution_limit_filter(export_quality: ExportQualitySettings) -> str:
    """Build a scale filter that only downsizes videos larger than the selected height."""

    if not export_quality.enabled or export_quality.resolution_limit == DEFAULT_RESOLUTION_LIMIT:
        return ""

    limit = RESOLUTION_LIMIT_HEIGHTS[export_quality.resolution_limit]
    return (
        "scale="
        f"w='if(gt(ih,{limit}),-2,iw)':"
        f"h='if(gt(ih,{limit}),{limit},ih)'"
    )
