"""CMDB 3D 机房布局 NATS 数据源接口测试。"""

from types import SimpleNamespace

import pytest

from apps.cmdb.nats import nats as N

USER_INFO = {"user": "alice", "team": 1, "domain": "local"}


def _room(inst_id=7, model_id="server_room"):
    return {"_id": inst_id, "model_id": model_id, "inst_name": "一号机房"}


def _rack(inst_id=5, location="A03"):
    return {
        "inst_id": str(inst_id),
        "inst_name": f"RACK-{inst_id}",
        "location": location,
        "datacenter_type": "2",
        "u_count": 42,
        "used_u": 21,
        "free_u": 21,
    }


def _install_permission(monkeypatch, allowed=True, permission_map=None):
    permission_map = permission_map or {1: {"permission_instances_map": {}, "inst_names": []}}
    monkeypatch.setattr(N, "_build_nats_permission_map", lambda *a, **k: permission_map)
    monkeypatch.setattr(N.InstanceManage, "_has_topology_view_permission", lambda *a, **k: allowed)
    monkeypatch.setattr(N.ExcludeFieldsCache, "get_model_attrs", lambda *a, **k: [])
    return permission_map


@pytest.mark.unit
def test_get_room3d_layout_ok_contract(monkeypatch):
    permission_map = _install_permission(monkeypatch)
    captured = {}

    def fake_get_room_layout(server_room_id, permission_map=None, user=None):
        captured["server_room_id"] = server_room_id
        captured["permission_map"] = permission_map
        captured["user"] = user
        return {"racks": [_rack()], "unplaced": [], "conflicts": [], "grid": {"max_row": 0, "max_col": 0}}

    def fake_get_room3d_rack_device_summaries(rack_ids, permission_map=None, user=None):
        captured["summary_rack_ids"] = rack_ids
        captured["summary_permission_map"] = permission_map
        captured["summary_user"] = user
        return {
            5: {
                "devices": [
                    {
                        "device_id": "10",
                        "device_name": "SW-01",
                        "model_id": "switch",
                        "rack_u_start": 1,
                        "u_size": 2,
                        "status": "running",
                    },
                ],
                "device_count": 2,
                "unplaced_device_count": 1,
            }
        }

    fake_rack_room = SimpleNamespace(
        get_room_layout=fake_get_room_layout,
        get_room3d_rack_device_summaries=fake_get_room3d_rack_device_summaries,
        get_rack_layout=lambda *a, **k: pytest.fail("Room3D 不应逐机柜调用 get_rack_layout"),
    )
    monkeypatch.setattr(N.InstanceManage, "query_entity_by_id", lambda pk: _room(pk))
    monkeypatch.setattr(N, "rack_room", fake_rack_room, raising=False)

    result = N.get_room3d_layout(server_room_id="7", user_info=USER_INFO)

    assert result["result"] is True
    assert result["message"] == ""
    assert result["data"] == {
        "room": {"id": "7", "name": "一号机房"},
        "racks": [
            {
                "rack_id": "5",
                "rack_name": "RACK-5",
                "row": 1,
                "col": 3,
                "location": "A03",
                "rack_type": "2",
                "u_count": 42,
                "used_u": 21,
                "free_u": 21,
                "device_count": 2,
                "unplaced_device_count": 1,
                "devices": [
                    {
                        "device_id": "10",
                        "device_name": "SW-01",
                        "model_id": "switch",
                        "rack_u_start": 1,
                        "u_size": 2,
                        "status": "running",
                    },
                ],
            }
        ],
    }
    assert captured["server_room_id"] == 7
    assert captured["permission_map"] is permission_map
    assert captured["user"].username == "alice"
    assert captured["user"].domain == "local"
    assert captured["summary_rack_ids"] == [5]
    assert captured["summary_permission_map"] is permission_map
    assert captured["summary_user"].username == "alice"


@pytest.mark.unit
def test_get_room3d_layout_falls_back_to_rack_id_when_name_missing(monkeypatch):
    _install_permission(monkeypatch)
    nameless_rack = _rack(5, "A03")
    nameless_rack["inst_name"] = ""
    monkeypatch.setattr(N.InstanceManage, "query_entity_by_id", lambda pk: _room(pk))
    monkeypatch.setattr(
        N,
        "rack_room",
        SimpleNamespace(
            get_room_layout=lambda *a, **k: {
                "racks": [nameless_rack],
                "unplaced": [],
                "conflicts": [],
                "grid": {"max_row": 0, "max_col": 0},
            },
            get_rack_layout=lambda *a, **k: {"placed": [], "unplaced": []},
        ),
        raising=False,
    )

    result = N.get_room3d_layout(server_room_id=7, user_info=USER_INFO)

    assert result["result"] is True
    assert result["data"]["racks"][0]["rack_id"] == "5"
    assert result["data"]["racks"][0]["rack_name"] == "5"


@pytest.mark.unit
def test_get_room3d_layout_returns_rack_type_name_from_cmdb_enum(monkeypatch):
    _install_permission(monkeypatch)
    monkeypatch.setattr(N.InstanceManage, "query_entity_by_id", lambda pk: _room(pk))
    monkeypatch.setattr(
        N.ExcludeFieldsCache,
        "get_model_attrs",
        lambda model_id: [
            {
                "attr_id": "datacenter_type",
                "attr_type": N.FIELD_TYPE_ENUM,
                "option": [
                    {"id": "1", "name": "计算"},
                    {"id": "2", "name": "网络"},
                ],
            }
        ]
        if model_id == "rack"
        else [],
    )
    monkeypatch.setattr(
        N,
        "rack_room",
        SimpleNamespace(
            get_room_layout=lambda *a, **k: {
                "racks": [_rack()],
                "unplaced": [],
                "conflicts": [],
                "grid": {"max_row": 0, "max_col": 0},
            },
            get_rack_layout=lambda *a, **k: {"placed": [], "unplaced": []},
        ),
        raising=False,
    )

    result = N.get_room3d_layout(server_room_id=7, user_info=USER_INFO)

    assert result["result"] is True
    assert result["data"]["racks"][0]["rack_type"] == "2"
    assert result["data"]["racks"][0]["rack_type_name"] == "网络"


@pytest.mark.unit
@pytest.mark.parametrize("value", [None, "", "abc"])
def test_get_room3d_layout_invalid_server_room_id(monkeypatch, value):
    _install_permission(monkeypatch)
    monkeypatch.setattr(N.InstanceManage, "query_entity_by_id", lambda pk: pytest.fail("不应查询实例"))

    result = N.get_room3d_layout(server_room_id=value, user_info=USER_INFO)

    assert result["result"] is False
    assert result["data"] == {}
    assert "server_room_id" in result["message"]


@pytest.mark.unit
def test_get_room3d_layout_missing_instance(monkeypatch):
    _install_permission(monkeypatch)
    monkeypatch.setattr(N.InstanceManage, "query_entity_by_id", lambda pk: None)

    result = N.get_room3d_layout(server_room_id=999, user_info=USER_INFO)

    assert result["result"] is False
    assert result["data"] == {}
    assert "不存在" in result["message"]


@pytest.mark.unit
def test_get_room3d_layout_rejects_non_server_room(monkeypatch):
    _install_permission(monkeypatch)
    monkeypatch.setattr(N.InstanceManage, "query_entity_by_id", lambda pk: _room(pk, model_id="rack"))

    result = N.get_room3d_layout(server_room_id=5, user_info=USER_INFO)

    assert result["result"] is False
    assert result["data"] == {}
    assert "server_room" in result["message"]


@pytest.mark.unit
def test_get_room3d_layout_denied_room(monkeypatch):
    _install_permission(monkeypatch, allowed=False)
    monkeypatch.setattr(N.InstanceManage, "query_entity_by_id", lambda pk: _room(pk))
    monkeypatch.setattr(
        N,
        "rack_room",
        SimpleNamespace(get_room_layout=lambda *a, **k: pytest.fail("无机房权限时不应继续查询布局")),
        raising=False,
    )

    result = N.get_room3d_layout(server_room_id=7, user_info=USER_INFO)

    assert result["result"] is False
    assert result["data"] == {}
    assert "无权限" in result["message"]


@pytest.mark.unit
def test_get_room3d_layout_empty_room(monkeypatch):
    _install_permission(monkeypatch)
    monkeypatch.setattr(N.InstanceManage, "query_entity_by_id", lambda pk: _room(pk))
    monkeypatch.setattr(
        N,
        "rack_room",
        SimpleNamespace(
            get_room_layout=lambda *a, **k: {"racks": [], "unplaced": [], "conflicts": [], "grid": {"max_row": 0, "max_col": 0}},
            _rack_device_instances=lambda *a, **k: pytest.fail("空机房不应计算设备数"),
        ),
        raising=False,
    )

    result = N.get_room3d_layout(server_room_id=7, user_info=USER_INFO)

    assert result == {
        "result": True,
        "data": {
            "room": {"id": "7", "name": "一号机房"},
            "racks": [],
        },
        "message": "",
    }


@pytest.mark.unit
def test_get_room3d_layout_uses_filtered_layout(monkeypatch):
    _install_permission(monkeypatch)
    monkeypatch.setattr(N.InstanceManage, "query_entity_by_id", lambda pk: _room(pk))
    monkeypatch.setattr(
        N,
        "rack_room",
        SimpleNamespace(
            get_room_layout=lambda *a, **k: {"racks": [], "unplaced": [], "conflicts": [], "grid": {"max_row": 0, "max_col": 0}},
            _rack_device_instances=lambda *a, **k: pytest.fail("被权限过滤的机柜不应再计算设备数"),
        ),
        raising=False,
    )

    result = N.get_room3d_layout(server_room_id=7, user_info=USER_INFO)

    assert result["result"] is True
    assert result["data"]["racks"] == []


@pytest.mark.unit
def test_get_room3d_layout_returns_conflicting_racks_for_frontend_resolution(monkeypatch):
    _install_permission(monkeypatch)
    captured_rack_ids = []
    monkeypatch.setattr(N.InstanceManage, "query_entity_by_id", lambda pk: _room(pk))
    monkeypatch.setattr(
        N,
        "rack_room",
        SimpleNamespace(
            get_room_layout=lambda *a, **k: {
                "racks": [_rack(5, "A03"), _rack(6, "A3"), _rack(7, "B01")],
                "unplaced": [],
                "conflicts": [],
                "grid": {"max_row": 0, "max_col": 0},
            },
            get_rack_layout=lambda rack_id, *a, **k: captured_rack_ids.append(rack_id) or {"placed": [], "unplaced": []},
            _rack_device_instances=lambda *a, **k: [],
        ),
        raising=False,
    )

    result = N.get_room3d_layout(server_room_id=7, user_info=USER_INFO)

    assert result["result"] is True
    assert [rack["rack_id"] for rack in result["data"]["racks"]] == ["5", "6", "7"]
    assert [(rack["row"], rack["col"], rack["location"]) for rack in result["data"]["racks"]] == [
        (1, 3, "A03"),
        (1, 3, "A03"),
        (2, 1, "B01"),
    ]
    assert "diagnostics" not in result["data"]
    assert captured_rack_ids == ["5", "6", "7"]


@pytest.mark.unit
def test_get_room3d_layout_reports_invalid_location_without_blocking_valid_racks(monkeypatch):
    _install_permission(monkeypatch)
    captured_rack_ids = []
    monkeypatch.setattr(N.InstanceManage, "query_entity_by_id", lambda pk: _room(pk))
    monkeypatch.setattr(
        N,
        "rack_room",
        SimpleNamespace(
            get_room_layout=lambda *a, **k: {
                "racks": [_rack(5, "库房暂存"), _rack(6, "A02")],
                "unplaced": [],
                "conflicts": [],
                "grid": {"max_row": 0, "max_col": 0},
            },
            get_rack_layout=lambda rack_id, *a, **k: captured_rack_ids.append(rack_id) or {"placed": [], "unplaced": []},
        ),
        raising=False,
    )

    result = N.get_room3d_layout(server_room_id=7, user_info=USER_INFO)

    assert result["result"] is True
    assert [rack["rack_id"] for rack in result["data"]["racks"]] == ["6"]
    assert captured_rack_ids == ["6"]
    assert "diagnostics" not in result["data"]
    assert "1 个机柜位置格式错误未展示" in result["data"]["notice"]
    assert "RACK-5" in result["data"]["notice"]


@pytest.mark.unit
def test_get_room3d_layout_formats_invalid_location_notice_in_english(monkeypatch):
    _install_permission(monkeypatch)
    monkeypatch.setattr(N.InstanceManage, "query_entity_by_id", lambda pk: _room(pk))
    monkeypatch.setattr(
        N,
        "rack_room",
        SimpleNamespace(
            get_room_layout=lambda *a, **k: {
                "racks": [_rack(5, "staging"), _rack(6, "")],
                "unplaced": [],
                "conflicts": [],
                "grid": {"max_row": 0, "max_col": 0},
            },
            get_rack_layout=lambda *a, **k: pytest.fail("无效位置不应继续查询机柜内设备"),
        ),
        raising=False,
    )

    result = N.get_room3d_layout(
        server_room_id=7,
        user_info={**USER_INFO, "locale": "en"},
    )

    assert result["result"] is True
    assert result["data"]["racks"] == []
    assert result["data"]["notice"] == (
        "2 racks have invalid locations and are not shown: " "RACK-5 (location is staging), RACK-6 (location is empty). " "Use the A3 / A03 format."
    )


@pytest.mark.unit
def test_get_room3d_layout_parses_letter_row_and_number_col(monkeypatch):
    _install_permission(monkeypatch)

    def fake_get_room_layout(*args, **kwargs):
        return {"racks": [_rack(5, "B21")], "unplaced": [], "conflicts": [], "grid": {"max_row": 0, "max_col": 0}}

    monkeypatch.setattr(N.InstanceManage, "query_entity_by_id", lambda pk: _room(pk))
    monkeypatch.setattr(
        N,
        "rack_room",
        SimpleNamespace(
            get_room_layout=fake_get_room_layout,
            get_rack_layout=lambda *a, **k: {"placed": [], "unplaced": []},
        ),
        raising=False,
    )

    result = N.get_room3d_layout(server_room_id=7, user_info=USER_INFO)

    assert result["result"] is True
    assert result["data"]["racks"][0]["row"] == 2
    assert result["data"]["racks"][0]["col"] == 21
    assert result["data"]["racks"][0]["location"] == "B21"


@pytest.mark.unit
def test_get_room3d_layout_accepts_unpadded_location_number(monkeypatch):
    _install_permission(monkeypatch)

    monkeypatch.setattr(N.InstanceManage, "query_entity_by_id", lambda pk: _room(pk))
    monkeypatch.setattr(
        N,
        "rack_room",
        SimpleNamespace(
            get_room_layout=lambda *a, **k: {"racks": [_rack(5, "A3")], "unplaced": [], "conflicts": [], "grid": {"max_row": 0, "max_col": 0}},
            get_rack_layout=lambda *a, **k: {"placed": [], "unplaced": []},
        ),
        raising=False,
    )

    result = N.get_room3d_layout(server_room_id=7, user_info=USER_INFO)

    assert result["result"] is True
    assert result["data"]["racks"][0]["row"] == 1
    assert result["data"]["racks"][0]["col"] == 3
    assert result["data"]["racks"][0]["location"] == "A03"


@pytest.mark.unit
def test_get_room3d_layout_reports_empty_location_as_notice(monkeypatch):
    _install_permission(monkeypatch)
    monkeypatch.setattr(N.InstanceManage, "query_entity_by_id", lambda pk: _room(pk))
    monkeypatch.setattr(
        N,
        "rack_room",
        SimpleNamespace(
            get_room_layout=lambda *a, **k: {
                "racks": [_rack(5, "")],
                "unplaced": [],
                "conflicts": [],
                "grid": {"max_row": 0, "max_col": 0},
            },
            get_rack_layout=lambda *a, **k: pytest.fail("位置为空时不应继续查询机柜内设备"),
        ),
        raising=False,
    )

    result = N.get_room3d_layout(server_room_id=7, user_info=USER_INFO)

    assert result["result"] is True
    assert result["data"]["racks"] == []
    assert "diagnostics" not in result["data"]
    assert "1 个机柜位置格式错误未展示" in result["data"]["notice"]
    assert "位置为空" in result["data"]["notice"]
