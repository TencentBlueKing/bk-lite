import pytest

from apps.alerts.action.exceptions import ConfigError
from apps.alerts.action.overrides import validate_manual_param_overrides
from apps.alerts.action.payload import build_match_payload, build_rule_payload, resolve_field, resolve_trigger_event_param
from apps.alerts.action.resolver import resolve_params


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
    assert not any(key.startswith("event.") for key in p)
    assert alert.events.mock_calls == []


@pytest.mark.parametrize("script_params", [[{"name": "origin"}], [{"name": "origin", "default": 99}]])
def test_action_parameters_keep_first_event_source_id(script_params):
    from types import SimpleNamespace

    from apps.alerts.action.resolver import resolve_params

    alert = FakeAlert()
    alert.events = SimpleNamespace(first=lambda: SimpleNamespace(source_id=7))

    params = resolve_params(build_match_payload(alert), [{"name": "origin", "from": "field", "value": "source_id"}], script_params)

    assert params == [{"name": "origin", "value": 7}]


def test_match_payload_flattens_representative_event_without_raw_data():
    from types import SimpleNamespace

    alert = FakeAlert()
    alert.events = SimpleNamespace(
        first=lambda: SimpleNamespace(
            source_id=7,
            source=SimpleNamespace(name="Prometheus"),
            event_id="EVENT-1",
            title="cpu",
            level="1",
            tags={"alert": "CpuHigh"},
            labels={},
            enrichment={"cmdb": {"owner": "张三"}},
            raw_data={"token": "secret-token-value"},
            assignee=["alice"],
            team=[1],
            ingest_key="abc",
        )
    )

    payload = build_match_payload(alert)

    assert payload["source_id"] == 7
    assert payload["event.event_id"] == "EVENT-1"
    assert payload["event.source_name"] == "Prometheus"
    assert payload["event.tags.alert"] == "CpuHigh"
    assert payload["event.enrichment.cmdb.owner"] == "张三"
    assert "event.raw_data" not in payload
    assert not any("secret-token-value" in str(value) for value in payload.values())
    assert "event.assignee" not in payload
    assert "event.ingest_key" not in payload


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


def test_resolve_params_uses_script_order_and_keeps_empty_const():
    payload = build_match_payload(FakeAlert())
    bindings = [
        {"name": "later", "from": "const", "value": "b"},
        {"name": "empty", "from": "const", "value": ""},
    ]
    script_params = [
        {"name": "empty", "default": "should-not-fill"},
        {"name": "later", "default": "x"},
        {"name": "added", "default": "from-script"},
    ]
    params = resolve_params(payload, bindings, script_params)
    assert params == [
        {"name": "empty", "value": ""},
        {"name": "later", "value": "b"},
        {"name": "added", "value": "from-script"},
    ]


def test_resolve_params_drops_removed_script_params_and_applies_overrides():
    payload = build_match_payload(FakeAlert())
    bindings = [
        {"name": "gone", "from": "const", "value": "old"},
        {"name": "keep", "from": "const", "value": "v1", "allow_adjust": True},
        {"name": "svc", "from": "field", "value": "labels.service"},
    ]
    script_params = [
        {"name": "keep", "default": "d"},
        {"name": "svc", "default": "nginx"},
    ]
    params = resolve_params(payload, bindings, script_params, overrides={"keep": "v2"})
    assert params == [
        {"name": "keep", "value": "v2"},
        {"name": "svc", "value": "nginx"},
    ]


def test_resolve_params_rejects_masked_default_as_real_value():
    payload = build_match_payload(FakeAlert())
    params = resolve_params(
        payload,
        [],
        [{"name": "token", "default": "******"}],
    )
    assert params == [{"name": "token", "value": ""}]


def test_field_missing_without_usable_default_is_config_error():
    payload = build_match_payload(FakeAlert())
    try:
        resolve_params(
            payload,
            [{"name": "origin", "from": "field", "value": "labels.missing"}],
            [{"name": "origin"}],
        )
    except ConfigError as exc:
        assert "origin" in str(exc)
    else:
        raise AssertionError("expected ConfigError")


def test_resolve_params_reads_trigger_event_from_payload():
    params = resolve_params(
        {"trigger_event": "closed"},
        [{"name": "event", "from": "field", "value": "trigger_event"}],
        [{"name": "event"}],
    )
    assert params == [{"name": "event", "value": "closed"}]


def test_resolve_trigger_event_param_keeps_lifecycle_event():
    execution = type("E", (), {"trigger_event": "closed"})()
    alert = type("A", (), {"status": "unassigned"})()
    assert resolve_trigger_event_param(execution, alert) == "closed"


def test_resolve_trigger_event_param_maps_manual_from_alert_status():
    execution = type("E", (), {"trigger_event": "manual"})()
    assert resolve_trigger_event_param(execution, type("A", (), {"status": "unassigned"})()) == "created"
    assert resolve_trigger_event_param(execution, type("A", (), {"status": "pending"})()) == "assigned"
    assert resolve_trigger_event_param(execution, type("A", (), {"status": "processing"})()) == "acknowledged"
    assert resolve_trigger_event_param(execution, type("A", (), {"status": "resolved"})()) == "resolved"
    assert resolve_trigger_event_param(execution, type("A", (), {"status": "closed"})()) == "closed"


def test_validate_manual_overrides_only_allows_adjustable_const():
    bindings = [
        {"name": "a", "from": "const", "value": "1", "allow_adjust": True},
        {"name": "b", "from": "const", "value": "2"},
        {"name": "c", "from": "field", "value": "title", "allow_adjust": True},
    ]
    validate_manual_param_overrides(bindings, {"a": "9"})
    try:
        validate_manual_param_overrides(bindings, {"b": "x"})
        raise AssertionError("b should be rejected")
    except ConfigError:
        pass
    try:
        validate_manual_param_overrides(bindings, {"c": "x"})
        raise AssertionError("field binding should be rejected")
    except ConfigError:
        pass
