import pytest

from src.time_utils import format_seconds, parse_timestamp


def test_parse_timestamp_accepts_mm_ss() -> None:
    assert parse_timestamp("02:30") == 150


def test_parse_timestamp_accepts_hh_mm_ss() -> None:
    assert parse_timestamp("01:02:03") == 3723


def test_parse_timestamp_strips_outer_whitespace() -> None:
    assert parse_timestamp(" 00:45 ") == 45


@pytest.mark.parametrize("value", ["", "   ", "2:30", "00:60", "10:99", "1:02:03"])
def test_parse_timestamp_rejects_invalid_values(value: str) -> None:
    with pytest.raises(ValueError):
        parse_timestamp(value)


def test_format_seconds_returns_hh_mm_ss() -> None:
    assert format_seconds(3723) == "01:02:03"
