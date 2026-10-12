import pytest

from src.time_utils import AR_INVALID_TIME_FORMAT, format_seconds, normalize_digits, normalize_timestamp_text, parse_timestamp


@pytest.mark.parametrize(
    ("value", "seconds"),
    [
        ("4:15", 255),
        ("04:15", 255),
        ("00:04:15", 255),
        ("1:04:15", 3855),
        ("١:٠٤:١٥", 3855),
        ("٤:١٥", 255),
        ("٠٤:١٥", 255),
    ],
)
def test_parse_timestamp_accepts_practical_time_inputs(value: str, seconds: int) -> None:
    assert parse_timestamp(value) == seconds


@pytest.mark.parametrize(
    ("value", "normalized"),
    [
        ("4:15", "00:04:15"),
        ("6:35", "00:06:35"),
        ("04:15", "00:04:15"),
        ("00:04:15", "00:04:15"),
        ("1:04:15", "01:04:15"),
        ("٤:١٥", "00:04:15"),
        ("04：15", "00:04:15"),
        ("04؛15", "00:04:15"),
    ],
)
def test_normalize_timestamp_text_returns_hh_mm_ss(value: str, normalized: str) -> None:
    assert normalize_timestamp_text(value) == normalized


def test_parse_timestamp_strips_outer_whitespace() -> None:
    assert parse_timestamp(" 00:45 ") == 45


@pytest.mark.parametrize("value", ["", "   ", "abc", "00:60", "10:99", "1:02:99", "1:2:3:4"])
def test_parse_timestamp_rejects_invalid_values(value: str) -> None:
    with pytest.raises(ValueError) as error:
        parse_timestamp(value)
    assert str(error.value) == AR_INVALID_TIME_FORMAT


def test_normalize_digits_supports_arabic_indic_digits() -> None:
    assert normalize_digits("٠١٢٣٤٥٦٧٨٩") == "0123456789"


def test_format_seconds_returns_hh_mm_ss() -> None:
    assert format_seconds(3723) == "01:02:03"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("00:37.5", 37.5),
        ("00:00:37.500", 37.5),
        ("01:02:03.125", 3723.125),
        ("٠٠:٣٧.٥", 37.5),
    ],
)
def test_subsecond_timestamps(value: str, expected: float) -> None:
    assert parse_timestamp(value) == expected
    assert parse_timestamp(normalize_timestamp_text(value)) == expected


def test_subsecond_formatter() -> None:
    assert format_seconds(37.5) == "00:00:37.500"
    assert format_seconds(59.999) == "00:00:59.999"
    assert format_seconds(60.0) == "00:01:00"


@pytest.mark.parametrize("invalid", ["00:12.1234", "00:61.25", "00:10.abc", "NaN"])
def test_invalid_fractions_rejected(invalid: str) -> None:
    with pytest.raises(ValueError):
        parse_timestamp(invalid)
