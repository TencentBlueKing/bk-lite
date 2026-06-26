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
