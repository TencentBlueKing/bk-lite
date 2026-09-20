from datetime import timedelta

import pytest

from apps.rum.services.query import MAX_RANGE_SPAN, parse_range_params


def _ms(dt) -> str:
    return str(int(dt.timestamp() * 1000))


def test_named_ranges_still_accepted():
    start, end = parse_range_params({"range": "7d"})
    assert end - start == timedelta(days=7)


def test_explicit_window_within_cap_is_accepted():
    _, now = parse_range_params({"range": "1h"})
    start = now - MAX_RANGE_SPAN
    parsed_start, parsed_end = parse_range_params({"from": _ms(start), "to": _ms(now)})
    assert parsed_end - parsed_start <= MAX_RANGE_SPAN


def test_explicit_window_over_cap_is_rejected():
    _, now = parse_range_params({"range": "1h"})
    start = now - MAX_RANGE_SPAN - timedelta(seconds=1)
    with pytest.raises(ValueError, match="maximum"):
        parse_range_params({"from": _ms(start), "to": _ms(now)})


@pytest.mark.parametrize(
    "raw_from,raw_to",
    [
        ("abc", "123"),
        ("10", "5"),
        ("99999999999999999999999", "99999999999999999999999999"),
    ],
)
def test_malformed_or_overflowing_timestamps_are_400_not_500(raw_from, raw_to):
    with pytest.raises(ValueError):
        parse_range_params({"from": raw_from, "to": raw_to})
