from apps.module_link.services.cmdb_monitor import _snapshot


def test_snapshot_uses_first_ip_from_list_or_ip_addr():
    listed = _snapshot(
        {"inst_uuid": "u-1", "model_id": "host", "inst_name": "h1", "ip": ["10.0.0.8", "10.0.0.9"]},
        "u-1",
    )
    assert listed["ip"] == "10.0.0.8"
    fallback = _snapshot({"inst_uuid": "u-2", "ip_addr": "10.0.0.7"}, "u-2")
    assert fallback["ip"] == "10.0.0.7"


def test_snapshot_keeps_port_or_listen_port():
    mysql = _snapshot({"inst_uuid": "u-db", "ip": "10.0.0.8", "port": 3306}, "u-db")
    assert mysql["port"] == "3306"
    nginx = _snapshot({"inst_uuid": "u-mw", "ip_addr": "10.0.0.9", "listen_port": "80"}, "u-mw")
    assert nginx["port"] == "80"
