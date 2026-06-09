"""Zabbix 告警源适配器覆盖测试。

对照 spec/prd/告警中心·集成：Zabbix webhook（含 ProblemId）归一化为标准事件，含恢复语义。
"""

import pytest

from apps.alerts.common.source_adapter.zabbix import ZabbixAdapter
from apps.alerts.models.alert_source import AlertSource
from apps.alerts.models.models import Level


@pytest.fixture
def event_levels(db):
    from apps.alerts.constants.constants import LevelType

    for lid in (0, 1, 2, 3):
        Level.objects.create(level_id=lid, level_name=f"L{lid}", level_display_name=f"等级{lid}", level_type=LevelType.EVENT)


@pytest.fixture
def zbx_source(db):
    return AlertSource.objects.create(
        name="zbx", source_id="zbx", source_type="zabbix", secret="sec",
        config={"event_fields_mapping": {}},
    )


def _adapter(zbx_source):
    return ZabbixAdapter(alert_source=zbx_source)


def test_is_english():
    assert ZabbixAdapter._is_english("en-US") is True
    assert ZabbixAdapter._is_english("zh-hans") is False
    assert ZabbixAdapter._is_english(None) is False


@pytest.mark.django_db
def test_normalize_payload_prefers_events(event_levels, zbx_source):
    a = _adapter(zbx_source)
    assert a.normalize_payload({"events": [{"title": "x"}]}) == [{"title": "x"}]


@pytest.mark.django_db
def test_normalize_payload_flat_problem(event_levels, zbx_source):
    a = _adapter(zbx_source)
    payload = {
        "ProblemId": "12345",
        "Subject": "高负载",
        "Message": "CPU过高",
        "Severity": "0",
        "HostName": "host1",
        "HostId": "10",
        "EventValue": "1",
    }
    events = a.normalize_payload(payload)
    assert len(events) == 1
    assert events[0]["external_id"] == "12345"
    assert events[0]["action"] == "created"
    assert events[0]["resource_name"] == "host1"


@pytest.mark.django_db
def test_normalize_payload_recovery(event_levels, zbx_source):
    a = _adapter(zbx_source)
    payload = {"ProblemId": "1", "Subject": "x", "Severity": "1", "EventValue": "0"}
    events = a.normalize_payload(payload)
    assert events[0]["action"] == "recovery"


@pytest.mark.django_db
def test_normalize_payload_single_event(event_levels, zbx_source):
    a = _adapter(zbx_source)
    payload = {"event": {"title": "x", "problem_id": "99"}, "EventValue": "1"}
    events = a.normalize_payload(payload)
    assert events[0]["external_id"] == "99"
    assert events[0]["action"] == "created"


@pytest.mark.django_db
def test_normalize_payload_missing_problem_id_raises(event_levels, zbx_source):
    a = _adapter(zbx_source)
    with pytest.raises(ValueError):
        a.normalize_payload({"Subject": "x"})


@pytest.mark.django_db
def test_test_connection_and_validate(event_levels, zbx_source):
    a = _adapter(zbx_source)
    assert a.test_connection() is True
    assert ZabbixAdapter.validate_config({}) is True


@pytest.mark.django_db
def test_get_integration_guide_en_and_zh(event_levels, zbx_source):
    a = _adapter(zbx_source)
    guide_en = a.get_integration_guide("http://host", language="en-US")
    guide_zh = a.get_integration_guide("http://host", language="zh-hans")
    assert guide_en["source_type"] == "zabbix"
    assert guide_zh["source_type"] == "zabbix"
