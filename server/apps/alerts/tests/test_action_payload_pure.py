import pytest

from apps.alerts.action.payload import build_match_payload, build_rule_payload, resolve_field


class FakeAlert:
    def __init__(self):
        self.alert_id = "A1"
        self.title = "disk full"
        self.level = "1"
        self.status = "unassigned"
        self.resource_id = "10"
        self.resource_name = "web-1"
        self.resource_type = "host"
        self.labels = {"ip": "10.0.0.5", "disk": 95, "service": "nginx"}
        self.enrichment = {"cmdb": {"owner": "zhang"}}


def test_top_level_and_dotted_keys():
    p = build_match_payload(FakeAlert())
    assert p["level"] == "1"
    assert p["title"] == "disk full"
    assert p["resource_type"] == "host"
    assert p["labels.ip"] == "10.0.0.5"
    assert p["labels.disk"] == 95
    assert p["enrichment.cmdb.owner"] == "zhang"


def test_resolve_field_dotted_and_missing():
    p = build_match_payload(FakeAlert())
    assert resolve_field(p, "labels.service") == "nginx"
    assert resolve_field(p, "labels.notexist") is None


def test_rule_payload_does_not_project_historical_source_fields_or_query_events():
    from unittest.mock import MagicMock

    alert = FakeAlert()
    alert.events = MagicMock()
    p = build_rule_payload(alert, include_source_names=False)
    assert "source_id" not in p and "source_pk" not in p
    assert alert.events.mock_calls == []


@pytest.mark.parametrize("script_params", [[{"name": "origin"}], [{"name": "origin", "default": 99}]])
def test_action_parameters_keep_first_event_source_id(script_params):
    from types import SimpleNamespace

    from apps.alerts.action.resolver import resolve_params

    alert = FakeAlert()
    alert.events = SimpleNamespace(first=lambda: SimpleNamespace(source_id=7))

    params = resolve_params(build_match_payload(alert), [{"name": "origin", "from": "field", "value": "source_id"}], script_params)

    assert params == [{"name": "origin", "value": 7}]


def test_payload_omits_source_id_when_no_events():
    """无关联事件时不应注入 source_id，避免误把 None 当成值参与比较。"""
    from unittest.mock import MagicMock

    alert = FakeAlert()
    alert.events = MagicMock()
    alert.events.first.return_value = None
    p = build_match_payload(alert)
    assert "source_id" not in p


def test_snapshot_source_name_and_unknown_source_id_fail_closed():
    """参数绑定保留单值快照，但它不再作为规则来源集合。"""
    from unittest.mock import MagicMock

    from apps.alerts.action.matcher import event_matches

    alert = MagicMock()
    alert.alert_id = "A1"
    alert.title = "t"
    alert.content = "c"
    alert.level = "1"
    alert.status = "pending"
    alert.resource_id = None
    alert.resource_name = None
    alert.resource_type = None
    alert.item = None
    alert.source_name = "NATS"
    alert.labels = {}
    alert.enrichment = {}

    evt = MagicMock()
    evt.source_id = 2
    alert.events = MagicMock()
    alert.events.first.return_value = evt

    p = build_match_payload(alert)
    # 旧快照条件不能代替关联来源集合
    assert event_matches(p, [[{"key": "source_name", "operator": "eq", "value": "NATS"}]]) is False
    # 老写法：source_id=2
    assert event_matches(p, [[{"key": "source_id", "operator": "eq", "value": 2}]]) is False
    # 不命中写法
    assert event_matches(p, [[{"key": "source_id", "operator": "eq", "value": 99}]]) is False
