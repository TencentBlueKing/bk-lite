"""Issue #4083: log policy timing JSON must match the worker contract."""

import pytest

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.log.serializers.policy import PolicySerializer
from apps.log.tasks.utils.policy import period_to_seconds


VALID_TIMING = {"type": "min", "value": 5}


@pytest.mark.parametrize(
    "field,value",
    [
        ("schedule", {"type": "min", "value": 0}),
        ("schedule", {"type": "week", "value": 1}),
        ("period", {"type": "min", "value": -1}),
        ("period", {"type": "min", "value": "5"}),
        ("period", {"type": "min"}),
    ],
)
def test_policy_serializer_rejects_invalid_timing_config(field, value):
    payload = {"schedule": VALID_TIMING, "period": VALID_TIMING, field: value}

    serializer = PolicySerializer(data=payload, partial=True)

    assert not serializer.is_valid()
    assert field in serializer.errors


def test_policy_serializer_accepts_supported_positive_integer_timing():
    serializer = PolicySerializer(
        data={
            "schedule": {"type": "hour", "value": 23},
            "period": {"type": "day", "value": 1},
        },
        partial=True,
    )

    assert serializer.is_valid(), serializer.errors


@pytest.mark.parametrize(
    "period",
    [
        {"type": "min", "value": 0},
        {"type": "min", "value": -1},
        {"type": "min", "value": "5"},
        {"type": "min", "value": True},
    ],
)
def test_period_to_seconds_rejects_values_that_cannot_form_a_scan_window(period):
    with pytest.raises(BaseAppException, match="period.value"):
        period_to_seconds(period)
