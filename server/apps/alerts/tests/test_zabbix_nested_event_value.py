"""嵌套 Zabbix 报文的 EventValue 为 0 时必须归一化为 recovery。"""

import pytest

from apps.alerts.common.source_adapter.zabbix import ZabbixAdapter
from apps.alerts.constants.constants import LevelType
from apps.alerts.models.alert_source import AlertSource
from apps.alerts.models.models import Level


@pytest.fixture
def event_levels(db):
    for lid in (0, 1, 2, 3):
        Level.objects.create(
            level_id=lid,
            level_name=f"L{lid}",
            level_display_name=f"等级{lid}",
            level_type=LevelType.EVENT,
        )


@pytest.fixture
def zbx_source(db):
    return AlertSource.objects.create(
        name="zbx",
        source_id="zbx",
        source_type="zabbix",
        secret="sec",
        config={"event_fields_mapping": {}},
    )


def _adapter(zbx_source):
    return ZabbixAdapter(alert_source=zbx_source)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("payload", "expected_action"),
    [
        pytest.param(
            {"event": {"title": "nested", "problem_id": "p1"}, "EventValue": 0},
            "recovery",
            id="outer-numeric-zero",
        ),
        pytest.param(
            {"event": {"title": "nested", "problem_id": "p1", "event_value": 0}},
            "recovery",
            id="inner-numeric-zero",
        ),
        pytest.param(
            {"event": {"title": "nested", "problem_id": "p1"}, "EventValue": "0"},
            "recovery",
            id="outer-string-zero",
        ),
        pytest.param(
            {"event": {"title": "nested", "problem_id": "p1"}, "EventValue": 1},
            "created",
            id="outer-numeric-one",
        ),
        pytest.param(
            {"event": {"title": "nested", "problem_id": "p1"}},
            "created",
            id="both-missing",
        ),
        pytest.param(
            {
                "event": {"title": "nested", "problem_id": "p1", "action": "created"},
                "EventValue": 0,
            },
            "created",
            id="explicit-action-kept",
        ),
        pytest.param(
            {
                "event": {"title": "nested", "problem_id": "p1", "event_value": 1},
                "EventValue": 0,
            },
            "recovery",
            id="outer-zero-beats-inner-one",
        ),
        pytest.param(
            {"ProblemId": "p1", "Subject": "flat", "EventValue": 0},
            "recovery",
            id="flat-numeric-zero",
        ),
        pytest.param(
            {
                "event": {"title": "nested", "problem_id": "p1", "event_value": 0},
                "EventValue": "   ",
            },
            "recovery",
            id="blank-outer-falls-through-to-inner-zero",
        ),
    ],
)
def test_nested_event_value_zero_selects_recovery(event_levels, zbx_source, payload, expected_action):
    events = _adapter(zbx_source).normalize_payload(payload)
    assert events[0]["action"] == expected_action
