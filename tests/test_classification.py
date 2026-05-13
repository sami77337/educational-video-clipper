import pytest

from src.classification import (
    ClassificationRule,
    ClassificationRuleError,
    classify_duration,
    get_default_classification_rules,
    sanitize_classification_folder_name,
    validate_classification_rules,
)


def test_default_classification_preserves_existing_behavior() -> None:
    rules = get_default_classification_rules()

    assert validate_classification_rules(rules) == []
    assert classify_duration(180, rules) == "ريلز"
    assert classify_duration(181, rules) == "فوائد"


def test_custom_three_rule_classification() -> None:
    rules = [
        ClassificationRule("Shorts", 0, 1, "Shorts"),
        ClassificationRule("ريلز", 1, 3, "ريلز"),
        ClassificationRule("فوائد", 3, None, "فوائد"),
    ]

    assert validate_classification_rules(rules) == []
    assert classify_duration(45, rules) == "Shorts"
    assert classify_duration(120, rules) == "ريلز"
    assert classify_duration(400, rules) == "فوائد"


def test_custom_ten_rule_classification() -> None:
    rules = [
        ClassificationRule(f"Rule {index}", index, index + 1, f"folder-{index}")
        for index in range(10)
    ]

    assert validate_classification_rules(rules) == []
    assert classify_duration(555, rules) == "folder-9"


def test_open_ended_final_rule() -> None:
    rules = [
        ClassificationRule("قصير", 0, 15, "قصير"),
        ClassificationRule("دروس", 15, None, "دروس"),
    ]

    assert validate_classification_rules(rules) == []
    assert classify_duration(60 * 30, rules) == "دروس"


def test_arabic_folder_names_are_supported_and_sanitized() -> None:
    assert sanitize_classification_folder_name("فوائد قصيرة: الجزء/الأول") == "فوائد قصيرة- الجزء-الأول"

    rules = [ClassificationRule("فوائد قصيرة", 0, None, "فوائد قصيرة")]
    assert validate_classification_rules(rules) == []
    assert classify_duration(90, rules) == "فوائد قصيرة"


def test_empty_rule_name_returns_error() -> None:
    errors = validate_classification_rules([ClassificationRule("", 0, 3, "ريلز")])

    assert any("rule name is empty" in error for error in errors)


def test_empty_folder_name_returns_error() -> None:
    errors = validate_classification_rules([ClassificationRule("ريلز", 0, 3, "   ")])

    assert any("folder name is empty" in error for error in errors)


def test_invalid_negative_ranges_return_errors() -> None:
    errors = validate_classification_rules([ClassificationRule("خطأ", -1, -2, "خطأ")])

    assert any("min_minutes cannot be negative" in error for error in errors)
    assert any("max_minutes must be a positive number" in error for error in errors)


def test_max_less_than_min_returns_error() -> None:
    errors = validate_classification_rules([ClassificationRule("خطأ", 7, 3, "خطأ")])

    assert any("max_minutes is less than min_minutes" in error for error in errors)


def test_overlapping_ranges_return_error() -> None:
    rules = [
        ClassificationRule("أول", 0, 5, "أول"),
        ClassificationRule("ثاني", 4, 10, "ثاني"),
    ]

    errors = validate_classification_rules(rules)

    assert any("overlaps" in error for error in errors)


def test_duplicate_sanitized_folder_names_return_error() -> None:
    rules = [
        ClassificationRule("أول", 0, 1, "lesson:one"),
        ClassificationRule("ثاني", 1, 2, "lesson/one"),
    ]

    errors = validate_classification_rules(rules)

    assert any("duplicate sanitized folder name" in error for error in errors)


def test_no_matching_rule_raises_error() -> None:
    rules = [ClassificationRule("قصير", 0, 1, "قصير")]

    with pytest.raises(ClassificationRuleError) as error:
        classify_duration(120, rules)

    assert "No classification rule can match duration" in str(error.value)
