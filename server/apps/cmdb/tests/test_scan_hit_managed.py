from types import SimpleNamespace

from apps.cmdb.services.scan_hit_managed import annotate_scan_hits_managed, match_scan_hit_entity


def _hit(**overrides):
    values = {
        "id": 1,
        "host": "10.0.1.10",
        "port": 0,
        "cmdb_model_id": "",
        "inst_uuid": "",
        "protocol": "host",
        "family_run": SimpleNamespace(model_id="host"),
        "snapshot": {},
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_match_prefers_inst_uuid():
    hit = _hit(inst_uuid="u-live", host="10.0.1.99")
    entities = [
        {"inst_uuid": "u-other", "model_id": "host", "ip_addr": "10.0.1.10"},
        {"inst_uuid": "u-live", "model_id": "switch", "ip_addr": "10.0.9.9"},
    ]
    assert match_scan_hit_entity(hit, entities)["inst_uuid"] == "u-live"


def test_match_host_by_ip_ignores_mysql_on_same_address():
    hit = _hit()
    entities = [
        {"inst_uuid": "u-db", "model_id": "mysql", "ip_addr": "10.0.1.10", "port": 3306},
        {"inst_uuid": "u-host", "model_id": "host", "ip_addr": "10.0.1.10"},
    ]
    assert match_scan_hit_entity(hit, entities)["inst_uuid"] == "u-host"


def test_match_mysql_requires_port():
    hit = _hit(protocol="mysql", family_run=SimpleNamespace(model_id="mysql"), cmdb_model_id="mysql", port=3306)
    entities = [
        {"inst_uuid": "u-wrong", "model_id": "mysql", "ip_addr": "10.0.1.10", "port": 3307},
        {"inst_uuid": "u-db", "model_id": "mysql", "ip_addr": "10.0.1.10", "port": 3306},
    ]
    assert match_scan_hit_entity(hit, entities)["inst_uuid"] == "u-db"
    hit.port = 0
    hit.snapshot = {}
    assert match_scan_hit_entity(hit, entities) is None


def test_match_untyped_network_accepts_any_network_model():
    hit = _hit(protocol="network", family_run=SimpleNamespace(model_id="network"), cmdb_model_id="")
    entities = [{"inst_uuid": "u-sw", "model_id": "switch", "ip_addr": "10.0.1.10"}]
    assert match_scan_hit_entity(hit, entities)["inst_uuid"] == "u-sw"


def test_match_physical_serial_across_ip():
    hit = _hit(
        protocol="physcial_server",
        family_run=SimpleNamespace(model_id="physcial_server"),
        host="10.0.1.10",
        snapshot={"serial_number": "SN-1"},
    )
    entities = [{"inst_uuid": "u-hw", "model_id": "physcial_server", "ip_addr": "10.0.1.8", "serial_number": "SN-1"}]
    assert match_scan_hit_entity(hit, entities)["inst_uuid"] == "u-hw"


def test_annotate_sets_cmdb_and_monitor_from_cmdb_id(monkeypatch):
    hit = _hit()
    monkeypatch.setattr(
        "apps.cmdb.services.scan_hit_managed._load_cmdb_entities",
        lambda hits, org_ids: [{"inst_uuid": "u-host", "model_id": "host", "ip_addr": "10.0.1.10"}],
    )
    monkeypatch.setattr(
        "apps.cmdb.services.scan_hit_managed._load_monitor_presence",
        lambda cmdb_ids, ips, org_ids: (set(cmdb_ids), set()),
    )
    annotate_scan_hits_managed([hit], SimpleNamespace(id=9, task=SimpleNamespace(team=[1])))
    assert hit.cmdb_managed is True
    assert hit.monitor_managed is True


def test_annotate_graph_monitor_id_skips_monitor_lookup(monkeypatch):
    hit = _hit()
    calls = []
    monkeypatch.setattr(
        "apps.cmdb.services.scan_hit_managed._load_cmdb_entities",
        lambda hits, org_ids: [{"inst_uuid": "u-host", "model_id": "host", "ip_addr": "10.0.1.10", "monitor_id": "m-1"}],
    )
    monkeypatch.setattr(
        "apps.cmdb.services.scan_hit_managed._load_monitor_presence",
        lambda cmdb_ids, ips, org_ids: calls.append((cmdb_ids, ips)) or (set(), set()),
    )
    annotate_scan_hits_managed([hit], SimpleNamespace(id=9, task=SimpleNamespace(team=[1])))
    assert hit.cmdb_managed is True
    assert hit.monitor_managed is True
    assert calls == [([], [])]


def test_annotate_monitor_by_ip_only_when_cmdb_missing(monkeypatch):
    hit = _hit()
    monkeypatch.setattr("apps.cmdb.services.scan_hit_managed._load_cmdb_entities", lambda hits, org_ids: [])
    monkeypatch.setattr(
        "apps.cmdb.services.scan_hit_managed._load_monitor_presence",
        lambda cmdb_ids, ips, org_ids: (set(), {"10.0.1.10"}),
    )
    annotate_scan_hits_managed([hit], SimpleNamespace(id=9, task=SimpleNamespace(team=[1])))
    assert hit.cmdb_managed is False
    assert hit.monitor_managed is True


def test_annotate_survives_lookup_errors(monkeypatch):
    hit = _hit()

    def _boom(*args, **kwargs):
        raise RuntimeError("graph down")

    monkeypatch.setattr("apps.cmdb.services.scan_hit_managed._load_cmdb_entities", _boom)
    monkeypatch.setattr("apps.cmdb.services.scan_hit_managed._load_monitor_presence", _boom)
    annotate_scan_hits_managed([hit], SimpleNamespace(id=9, task=SimpleNamespace(team=[1])))
    assert hit.cmdb_managed is False
    assert hit.monitor_managed is False
