import pytest

from apps.monitor.expression.conditions import compile_filter_to_selectors


def test_compile_all_and_conditions_to_one_selector():
    selectors = compile_filter_to_selectors(
        "http_requests_total{__$labels__}",
        [
            {"name": "service", "method": "=", "value": "checkout"},
            {"logic": "and", "name": "status", "method": "=~", "value": "5.."},
        ],
    )

    assert selectors == ['http_requests_total{service="checkout",status=~"5.."}']


def test_compile_or_conditions_to_selector_union():
    selectors = compile_filter_to_selectors(
        "http_requests_total{__$labels__}",
        [
            {"name": "service", "method": "=", "value": "checkout"},
            {"logic": "and", "name": "status", "method": "=~", "value": "5.."},
            {"logic": "or", "name": "status", "method": "=", "value": "499"},
        ],
    )

    assert selectors == [
        'http_requests_total{service="checkout",status=~"5.."}',
        'http_requests_total{status="499"}',
    ]


def test_compile_empty_filter_keeps_placeholder_empty_selector():
    assert compile_filter_to_selectors("up{__$labels__}", []) == ["up{}"]


def test_reject_invalid_logic():
    with pytest.raises(ValueError) as exc:
        compile_filter_to_selectors("up{__$labels__}", [{"logic": "xor", "name": "a", "method": "=", "value": "b"}])

    assert "logic" in str(exc.value)
