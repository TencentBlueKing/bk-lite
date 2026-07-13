from apps.alerts.action.payload import build_match_payload, resolve_field


class FakeAlert:
    def __init__(self):
        self.alert_id = "A1"; self.title = "disk full"; self.level = "1"
        self.status = "unassigned"; self.resource_id = "10"; self.resource_name = "web-1"
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


def test_payload_exposes_source_id_from_first_event_when_events_present():
    """rules 可能用 key='source_id' 过滤（虽然推荐 key='source_name'）。
    当 alert 有关联事件时，payload 应把第一条的 source_id 暴露出去，
    让 evaluate 能命中 match_rules 的 source_id 写法（向后兼容老数据）。"""
    from unittest.mock import MagicMock

    alert = FakeAlert()
    first_evt = MagicMock()
    first_evt.source_id = 7
    alert.events = MagicMock()
    alert.events.first.return_value = first_evt

    p = build_match_payload(alert)
    assert p["source_id"] == 7
    # source_name 必须已经存在（来自 TOP_FIELDS）
    # 上面的 FakeAlert 没有 source_name；这里只校验 source_id 注入，不强求 source_name


def test_payload_omits_source_id_when_no_events():
    """无关联事件时不应注入 source_id，避免误把 None 当成值参与比较。"""
    from unittest.mock import MagicMock
    alert = FakeAlert()
    alert.events = MagicMock()
    alert.events.first.return_value = None
    p = build_match_payload(alert)
    assert "source_id" not in p


def test_source_name_preferred_id_legacy_supported_via_match():
    """业务一致性：source_name 仍是首选可匹配 key，同时 source_id 也可匹配（向后兼容）。"""
    from apps.alerts.enrichment.matcher import event_matches
    from unittest.mock import MagicMock

    alert = MagicMock()
    alert.alert_id = "A1"
    alert.title = "t"; alert.content = "c"; alert.level = "1"
    alert.status = "pending"
    alert.resource_id = None; alert.resource_name = None
    alert.resource_type = None; alert.item = None; alert.source_name = "NATS"
    alert.labels = {}; alert.enrichment = {}

    evt = MagicMock()
    evt.source_id = 2
    alert.events = MagicMock()
    alert.events.first.return_value = evt

    p = build_match_payload(alert)
    # 推荐写法：source_name=NATS
    assert event_matches(p, [[{"key": "source_name", "operator": "eq", "value": "NATS"}]]) is True
    # 老写法：source_id=2
    assert event_matches(p, [[{"key": "source_id", "operator": "eq", "value": 2}]]) is True
    # 不命中写法
    assert event_matches(p, [[{"key": "source_id", "operator": "eq", "value": 99}]]) is False
