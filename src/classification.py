"""Duration-based clip classification rules."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from numbers import Real

from src.file_utils import sanitize_filename


DEFAULT_REELS_RULE_NAME = "ريلز"
DEFAULT_BENEFITS_RULE_NAME = "فوائد"


@dataclass(frozen=True)
class ClassificationRule:
    """A duration range that maps clips to an output folder."""

    name: str
    min_minutes: float
    max_minutes: float | None
    folder_name: str


class ClassificationRuleError(ValueError):
    """Raised when classification rules cannot classify a clip."""


def get_default_classification_rules() -> list[ClassificationRule]:
    """Return rules that preserve the existing ريلز / فوائد behavior."""

    return [
        ClassificationRule(
            name=DEFAULT_REELS_RULE_NAME,
            min_minutes=0,
            max_minutes=3,
            folder_name=DEFAULT_REELS_RULE_NAME,
        ),
        ClassificationRule(
            name=DEFAULT_BENEFITS_RULE_NAME,
            min_minutes=3,
            max_minutes=None,
            folder_name=DEFAULT_BENEFITS_RULE_NAME,
        ),
    ]


def validate_classification_rules(rules: Sequence[ClassificationRule]) -> list[str]:
    """Return clear validation errors for classification rules."""

    errors: list[str] = []
    normalized_ranges: list[tuple[int, float, float | None]] = []
    sanitized_folders: dict[str, int] = {}

    if not rules:
        return ["At least one classification rule is required."]

    for index, rule in enumerate(rules, start=1):
        prefix = f"Rule {index}"

        if not _has_text(rule.name):
            errors.append(f"{prefix}: rule name is empty.")

        if not _has_text(rule.folder_name):
            errors.append(f"{prefix}: folder name is empty.")
        else:
            sanitized_folder = _sanitize_folder_for_validation(rule.folder_name)
            if not sanitized_folder:
                errors.append(f"{prefix}: folder name is empty after Windows path sanitization.")
            else:
                folder_key = sanitized_folder.casefold()
                previous_index = sanitized_folders.get(folder_key)
                if previous_index is not None:
                    errors.append(
                        f"{prefix}: duplicate sanitized folder name with rule {previous_index}: "
                        f"{sanitized_folder}."
                    )
                else:
                    sanitized_folders[folder_key] = index

        min_minutes = _coerce_minutes(rule.min_minutes)
        max_minutes = _coerce_minutes(rule.max_minutes, allow_none=True)

        if min_minutes is None:
            errors.append(f"{prefix}: min_minutes is missing or invalid.")
        elif min_minutes < 0:
            errors.append(f"{prefix}: min_minutes cannot be negative.")

        if rule.max_minutes is not None and max_minutes is None:
            errors.append(f"{prefix}: max_minutes is invalid.")
        elif max_minutes is not None and max_minutes <= 0:
            errors.append(f"{prefix}: max_minutes must be a positive number.")

        if min_minutes is not None and max_minutes is not None and max_minutes < min_minutes:
            errors.append(f"{prefix}: max_minutes is less than min_minutes.")

        if min_minutes is not None and min_minutes >= 0:
            if max_minutes is None or max_minutes > 0:
                if max_minutes is None or max_minutes >= min_minutes:
                    normalized_ranges.append((index, min_minutes, max_minutes))

    errors.extend(_find_overlap_errors(normalized_ranges))
    return errors


def classify_duration(
    duration_seconds: int | float,
    rules: Sequence[ClassificationRule] | None = None,
) -> str:
    """Return the sanitized folder name for the first rule matching a duration."""

    if not _is_real_number(duration_seconds) or duration_seconds < 0:
        raise ClassificationRuleError("Duration seconds must be zero or greater.")

    active_rules = get_default_classification_rules() if rules is None else list(rules)
    errors = validate_classification_rules(active_rules)
    if errors:
        raise ClassificationRuleError("\n".join(errors))

    duration_minutes = float(duration_seconds) / 60
    for rule in active_rules:
        min_minutes = float(rule.min_minutes)
        max_minutes = None if rule.max_minutes is None else float(rule.max_minutes)
        if _matches_rule(duration_minutes, min_minutes, max_minutes):
            return sanitize_classification_folder_name(rule.folder_name)

    raise ClassificationRuleError(f"No classification rule can match duration {duration_seconds} seconds.")


def sanitize_classification_folder_name(name: str) -> str:
    """Return a Windows-safe folder name for a classification rule."""

    return sanitize_filename(str(name), default="category")


def _find_overlap_errors(ranges: list[tuple[int, float, float | None]]) -> list[str]:
    errors: list[str] = []
    for first_position, (first_index, first_min, first_max) in enumerate(ranges):
        for second_index, second_min, second_max in ranges[first_position + 1 :]:
            if _ranges_overlap(first_min, first_max, second_min, second_max):
                errors.append(f"Rule {second_index}: duration range overlaps with rule {first_index}.")
    return errors


def _ranges_overlap(
    first_min: float,
    first_max: float | None,
    second_min: float,
    second_max: float | None,
) -> bool:
    # Shared boundaries are allowed because first-match classification keeps them deterministic.
    if first_max is not None and first_max <= second_min:
        return False
    if second_max is not None and second_max <= first_min:
        return False
    return True


def _matches_rule(duration_minutes: float, min_minutes: float, max_minutes: float | None) -> bool:
    if duration_minutes < min_minutes:
        return False
    if max_minutes is None:
        return True
    return duration_minutes <= max_minutes


def _coerce_minutes(value: object, allow_none: bool = False) -> float | None:
    if value is None:
        return None if allow_none else None
    if not _is_real_number(value):
        return None
    return float(value)


def _is_real_number(value: object) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool)


def _has_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _sanitize_folder_for_validation(name: str) -> str:
    return sanitize_filename(name, default="")
