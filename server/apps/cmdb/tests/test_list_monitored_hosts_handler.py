from apps.cmdb.nats import nats as nats


def _stub_ensure(monkeypatch):
    calls = []

    def fake_ensure(**kwargs):
        calls.append(kwargs)
        return True

    monkeypatch.setattr(nats, "ensure_host_zombie_whitelist_attr", fake_ensure, raising=False)
    monkeypatch.setattr(
        "apps.cmdb.services.host_zombie_whitelist.ensure_host_zombie_whitelist_attr",
        fake_ensure,
    )
    return calls


class _GroupQuery:
    def __init__(self, rows):
        self._rows = rows

    def values(self, *fields):
        return self._rows


def _stub_groups(monkeypatch, rows=None):
    rows = rows if rows is not None else [{"id": 1, "name": "交易"}]
    monkeypatch.setattr(nats.Group.objects, "filter", lambda **kw: _GroupQuery(rows))


def test_list_monitored_hosts_omits_empty_monitor_id(monkeypatch):
    ensure_calls = _stub_ensure(monkeypatch)
    _stub_groups(monkeypatch)
    captured = {}

    def fake_instance_list(*args, **kw):
        captured["args"] = args
        captured["kw"] = kw
        return (
            [
                {
                    "inst_uuid": "u1",
                    "inst_name": "h1",
                    "ip_addr": "10.0.0.1",
                    "os_type": "2",
                    "monitor_id": "m1",
                    "organization": [1],
                },
                {
                    "inst_uuid": "u2",
                    "inst_name": "h2",
                    "ip_addr": "10.0.0.2",
                    "os_type": "1",
                    "monitor_id": "",
                    "organization": [1],
                },
            ],
            2,
        )

    monkeypatch.setattr(nats, "_build_nats_permission_map", lambda user_info, **kw: {"ok": True})
    monkeypatch.setattr(nats.InstanceManage, "instance_list", fake_instance_list)

    out = nats.list_monitored_hosts(user_info={"user": "u", "team": 1})

    assert ensure_calls, "ensure_host_zombie_whitelist_attr must run on handler entry"
    assert captured["kw"]["model_id"] == "host"
    assert captured["kw"]["params"] == []
    assert captured["kw"]["page"] == 1
    assert captured["kw"]["page_size"] == 5000
    assert captured["kw"]["order"] == "inst_name"
    assert captured["kw"]["permission_map"] == {"ok": True}
    assert out["result"] is True
    assert out["message"] == ""
    assert [row["inst_uuid"] for row in out["data"]] == ["u1"]
    assert out["data"][0]["monitor_id"] == "m1"
    assert out["data"][0]["display_name"] == "h1 (10.0.0.1)"
    assert out["data"][0]["biz_name"] == "交易"


def test_list_monitored_hosts_empty_permission_returns_empty(monkeypatch):
    ensure_calls = _stub_ensure(monkeypatch)
    queried = {"called": False}

    def fake_instance_list(*args, **kw):
        queried["called"] = True
        return ([], 0)

    monkeypatch.setattr(nats, "_build_nats_permission_map", lambda user_info, **kw: None)
    monkeypatch.setattr(nats.InstanceManage, "instance_list", fake_instance_list)

    out = nats.list_monitored_hosts(user_info={})

    assert ensure_calls, "ensure_host_zombie_whitelist_attr must run even on empty permission"
    assert queried["called"] is False
    assert out == {"result": True, "data": [], "message": ""}


def test_list_application_systems_returns_authorized_rows(monkeypatch):
    captured = {}

    def fake_instance_list(*args, **kw):
        captured["kw"] = kw
        return (
            [
                {"inst_uuid": "s1", "inst_name": "sys-ecom"},
                {"inst_uuid": "", "inst_name": "skip"},
            ],
            2,
        )

    monkeypatch.setattr(nats, "_build_nats_permission_map", lambda user_info, **kw: {"ok": True})
    monkeypatch.setattr(nats.InstanceManage, "instance_list", fake_instance_list)

    out = nats.list_application_systems(user_info={"user": "u", "team": 1})

    assert captured["kw"]["model_id"] == "system"
    assert captured["kw"]["page_size"] == 5000
    assert captured["kw"]["permission_map"] == {"ok": True}
    assert out == {
        "result": True,
        "data": [{"inst_uuid": "s1", "inst_name": "sys-ecom", "display_name": "sys-ecom"}],
        "message": "",
    }


def test_list_application_systems_empty_permission_returns_empty(monkeypatch):
    queried = {"called": False}

    def fake_instance_list(*args, **kw):
        queried["called"] = True
        return ([], 0)

    monkeypatch.setattr(nats, "_build_nats_permission_map", lambda user_info, **kw: None)
    monkeypatch.setattr(nats.InstanceManage, "instance_list", fake_instance_list)

    out = nats.list_application_systems(user_info={})

    assert queried["called"] is False
    assert out == {"result": True, "data": [], "message": ""}


def test_list_host_uuids_for_systems_omits_unauthorized_and_expands(monkeypatch):
    def fake_instance_list(*args, **kw):
        return ([{"inst_uuid": "s1", "inst_name": "sys-ecom"}], 1)

    monkeypatch.setattr(nats, "_build_nats_permission_map", lambda user_info, **kw: {"ok": True})
    monkeypatch.setattr(nats.InstanceManage, "instance_list", fake_instance_list)
    monkeypatch.setattr(
        nats,
        "expand_systems_to_host_uuids",
        lambda selected, **kw: ["h1", "h2"] if selected == ["s1"] else [],
    )

    out = nats.list_host_uuids_for_systems(
        system_uuids=["s1", "s-missing"],
        user_info={"user": "u", "team": 1},
    )

    assert out["result"] is True
    assert out["message"] == ""
    assert [row["inst_uuid"] for row in out["data"]] == ["h1", "h2"]


def test_list_host_uuids_for_systems_rejects_non_list():
    out = nats.list_host_uuids_for_systems(system_uuids="s1", user_info={"user": "u", "team": 1})
    assert out["result"] is False
    assert out["data"] == []
    assert "列表" in out["message"]


def test_list_host_uuids_for_systems_empty_selection_is_empty_success(monkeypatch):
    monkeypatch.setattr(nats, "_build_nats_permission_map", lambda user_info, **kw: {"ok": True})
    queried = {"called": False}

    def fake_instance_list(*args, **kw):
        queried["called"] = True
        return ([], 0)

    monkeypatch.setattr(nats.InstanceManage, "instance_list", fake_instance_list)
    out = nats.list_host_uuids_for_systems(system_uuids=[], user_info={"user": "u", "team": 1})
    assert out == {"result": True, "data": [], "message": ""}
    assert queried["called"] is False


def test_list_monitored_hosts_for_systems_returns_rows_and_expanded_count(monkeypatch):
    _stub_ensure(monkeypatch)
    _stub_groups(monkeypatch)
    captured = {}

    def fake_instance_list(*args, **kw):
        captured["system_kw"] = kw
        return ([{"inst_uuid": "s1", "inst_name": "sys-ecom"}], 1)

    def fake_entities(inst_uuids):
        captured["host_uuids"] = list(inst_uuids)
        return [
            {
                "inst_uuid": "h1",
                "model_id": "host",
                "inst_name": "web-1",
                "ip_addr": "10.0.0.1",
                "os_type": "1",
                "monitor_id": "m1",
                "organization": [1],
            },
            {
                "inst_uuid": "h2",
                "model_id": "host",
                "inst_name": "web-2",
                "ip_addr": "10.0.0.2",
                "os_type": "1",
                "monitor_id": "",
                "organization": [1],
            },
        ]

    monkeypatch.setattr(nats, "_build_nats_permission_map", lambda user_info, **kw: {"ok": True})
    monkeypatch.setattr(nats.InstanceManage, "instance_list", fake_instance_list)
    monkeypatch.setattr(nats, "expand_systems_to_host_uuids", lambda selected, **kw: ["h1", "h2", "h3"])
    monkeypatch.setattr(nats.InstanceManage, "query_entity_by_uuids", fake_entities)
    monkeypatch.setattr(nats.InstanceManage, "_has_topology_view_permission", lambda *a, **k: True)

    out = nats.list_monitored_hosts_for_systems(
        system_uuids=["s1", "s-missing"],
        user_info={"user": "u", "team": 1},
    )

    assert captured["system_kw"]["model_id"] == "system"
    assert captured["host_uuids"] == ["h1", "h2", "h3"]
    assert out["result"] is True
    assert out["message"] == ""
    assert out["data"]["expanded_host_count"] == 3
    assert [row["inst_uuid"] for row in out["data"]["items"]] == ["h1"]
    assert out["data"]["items"][0]["monitor_id"] == "m1"
    assert out["data"]["items"][0]["biz_name"] == "交易"


def test_list_monitored_hosts_for_systems_rejects_non_list():
    out = nats.list_monitored_hosts_for_systems(system_uuids="s1", user_info={"user": "u", "team": 1})
    assert out["result"] is False
    assert out["data"] == {"items": [], "expanded_host_count": 0}
    assert "列表" in out["message"]


def test_list_monitored_hosts_for_systems_empty_selection_is_empty_success(monkeypatch):
    queried = {"called": False}

    def fake_instance_list(*args, **kw):
        queried["called"] = True
        return ([], 0)

    monkeypatch.setattr(nats, "_build_nats_permission_map", lambda user_info, **kw: {"ok": True})
    monkeypatch.setattr(nats.InstanceManage, "instance_list", fake_instance_list)
    out = nats.list_monitored_hosts_for_systems(system_uuids=[], user_info={"user": "u", "team": 1})
    assert out == {"result": True, "data": {"items": [], "expanded_host_count": 0}, "message": ""}
    assert queried["called"] is False


def test_list_monitored_hosts_for_systems_drops_unauthorized_hosts(monkeypatch):
    _stub_ensure(monkeypatch)
    _stub_groups(monkeypatch)

    monkeypatch.setattr(nats, "_build_nats_permission_map", lambda user_info, **kw: {"ok": True})
    monkeypatch.setattr(
        nats.InstanceManage,
        "instance_list",
        lambda *args, **kw: ([{"inst_uuid": "s1", "inst_name": "sys-ecom"}], 1),
    )
    monkeypatch.setattr(nats, "expand_systems_to_host_uuids", lambda selected, **kw: ["h1", "h2"])
    monkeypatch.setattr(
        nats.InstanceManage,
        "query_entity_by_uuids",
        lambda inst_uuids: [
            {
                "inst_uuid": "h1",
                "model_id": "host",
                "inst_name": "keep",
                "ip_addr": "10.0.0.1",
                "os_type": "1",
                "monitor_id": "m1",
                "organization": [1],
            },
            {
                "inst_uuid": "h2",
                "model_id": "host",
                "inst_name": "drop",
                "ip_addr": "10.0.0.2",
                "os_type": "1",
                "monitor_id": "m2",
                "organization": [1],
            },
        ],
    )
    monkeypatch.setattr(
        nats.InstanceManage,
        "_has_topology_view_permission",
        lambda entity, permission_map, user=None: entity.get("inst_uuid") == "h1",
    )

    out = nats.list_monitored_hosts_for_systems(system_uuids=["s1"], user_info={"user": "u", "team": 1})
    assert [row["inst_uuid"] for row in out["data"]["items"]] == ["h1"]
    assert out["data"]["expanded_host_count"] == 2
