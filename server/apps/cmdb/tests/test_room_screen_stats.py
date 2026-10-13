from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.cmdb.services.instance_scope import resolve_room_rack_devices
from apps.cmdb.services.room_screen_stats import MONITOR_ID_BATCH_SIZE, room_active_alarms, room_device_type_distribution, room_rack_capacity

ROOM = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"
RACK_A = "33333333-3333-4333-8333-333333333333"
RACK_B = "44444444-4444-4444-8444-444444444444"
DEV_A = "55555555-5555-4555-8555-555555555555"
DEV_B = "66666666-6666-4666-8666-666666666666"
DEV_DIRECT = "77777777-7777-4777-8777-777777777777"


def _uuid(value: int) -> str:
    return f"00000000-0000-4000-8000-{value:012d}"


def _graph(edges_by_query):
    client = MagicMock()

    def query_edge(_label, query):
        src_model = next(item["value"] for item in query if item["field"] == "src_model_id")
        dst_model = next((item["value"] for item in query if item["field"] == "dst_model_id"), None)
        return edges_by_query.get((src_model, dst_model), [])

    client.query_edge.side_effect = query_edge
    context = MagicMock()
    context.__enter__.return_value = client
    context.__exit__.return_value = False
    return context, client


def _parse_locator(value):
    from apps.cmdb.nats.nats import _parse_room3d_server_room_locator

    return _parse_room3d_server_room_locator(value)


@pytest.mark.unit
def test_room_scope_batches_edges_and_skips_devices_not_in_racks():
    room_edges = [
        {"src_inst_uuid": ROOM, "dst_inst_uuid": RACK_A, "dst_model_id": "rack"},
        {"src_inst_uuid": ROOM, "dst_inst_uuid": RACK_B, "dst_model_id": "rack"},
        {"src_inst_uuid": ROOM, "dst_inst_uuid": DEV_DIRECT, "dst_model_id": "host"},
    ]
    device_edges = [
        {"src_inst_uuid": RACK_A, "dst_inst_uuid": DEV_A},
        {"src_inst_uuid": RACK_B, "dst_inst_uuid": DEV_B},
        {"src_inst_uuid": DEV_A, "dst_inst_uuid": "88888888-8888-4888-8888-888888888888"},
    ]
    context, client = _graph({("server_room", "rack"): room_edges, ("rack", None): device_edges})
    instances = {
        RACK_A: {"inst_uuid": RACK_A, "model_id": "rack", "inst_name": "A01", "u_count": 10},
        RACK_B: {"inst_uuid": RACK_B, "model_id": "rack", "inst_name": "A02", "u_count": 10, "_id": 2},
        DEV_A: {"inst_uuid": DEV_A, "model_id": "host", "inst_name": "srv", "rack_u_start": 1, "u_size": 2},
        DEV_B: {"inst_uuid": DEV_B, "model_id": "switch", "inst_name": "sw", "rack_u_start": None, "u_size": 1},
        DEV_DIRECT: {"inst_uuid": DEV_DIRECT, "model_id": "host", "inst_name": "loose"},
    }

    def visible(uuids):
        return [instances[item] for item in uuids if item in instances]

    def allow(instance, permission_map, user=None):
        return instance.get("_id") != 2

    with (
        patch("apps.cmdb.services.instance_scope.GraphClient", return_value=context),
        patch("apps.cmdb.services.instance_scope.InstanceManage.query_entity_by_uuids", side_effect=visible),
        patch("apps.cmdb.services.instance_scope.InstanceManage._has_topology_view_permission", side_effect=allow),
    ):
        scope = resolve_room_rack_devices(ROOM, permission_map={"x": 1}, user=None)

    assert client.query_edge.call_count == 2
    assert [item["inst_uuid"] for item in scope.racks] == [RACK_A]
    assert [item["inst_uuid"] for item in scope.devices_by_rack_uuid[RACK_A]] == [DEV_A]
    assert DEV_DIRECT not in {item["inst_uuid"] for item in scope.devices_by_rack_uuid[RACK_A]}


@pytest.mark.unit
def test_capacity_summary_counts_unracked_and_distinct_u():
    rack = {"inst_uuid": RACK_A, "model_id": "rack", "inst_name": "A01", "u_count": 10}
    devices = [
        {"inst_uuid": DEV_A, "rack_u_start": 1, "u_size": 2},
        {"inst_uuid": DEV_B, "rack_u_start": 2, "u_size": 2},
        {"inst_uuid": DEV_DIRECT, "rack_u_start": None, "u_size": 4},
    ]
    scope = SimpleNamespace(racks=[rack], devices_by_rack_uuid={RACK_A: devices})
    room = {"inst_uuid": ROOM, "model_id": "server_room", "inst_name": "一号"}
    later = {"inst_uuid": OTHER, "model_id": "server_room", "inst_name": "二号"}
    with (
        patch("apps.cmdb.services.room_screen_stats.list_server_rooms", return_value=[room, later]),
        patch("apps.cmdb.services.room_screen_stats.InstanceManage.query_entity_by_uuid", return_value=room),
        patch("apps.cmdb.services.room_screen_stats.InstanceManage._has_topology_view_permission", return_value=True),
        patch("apps.cmdb.services.room_screen_stats.resolve_room_rack_devices", return_value=scope) as resolve,
    ):
        summary = room_rack_capacity(
            server_room_id=ROOM,
            view="summary",
            permission_map={"10": {}},
            user=None,
            parse_locator=_parse_locator,
        )
        top = room_rack_capacity(
            server_room_id="",
            view="rack_top",
            limit=5,
            permission_map={"10": {}},
            user=None,
            parse_locator=_parse_locator,
        )
    assert summary["result"] is True
    # U1-2 与 U2-3 去重后占用 3，未上架 1，不把直接占用相加
    assert summary["data"] == {
        "rack_count": 1,
        "device_count": 3,
        "unracked_device_count": 1,
        "total_u": 10,
        "used_u": 3,
        "free_u": 7,
        "u_usage_percent": 30,
    }
    assert top["data"] == [{"name": "A01", "value": 30, "used_u": 3, "u_count": 10}]
    assert resolve.call_args_list[-1].args[0] == ROOM


@pytest.mark.unit
def test_invisible_room_and_empty_permission_do_not_fall_through():
    with patch("apps.cmdb.services.room_screen_stats.InstanceManage.query_entity_by_uuid", return_value=None):
        missing = room_rack_capacity(server_room_id=ROOM, view="summary", permission_map={"10": {}}, user=None, parse_locator=_parse_locator)
    assert missing["result"] is False
    assert missing["code"] == 404
    denied = room_rack_capacity(server_room_id=ROOM, view="summary", permission_map=None, user=None, parse_locator=_parse_locator)
    assert denied["code"] == 403


@pytest.mark.unit
def test_group_by_model_uses_localized_display_name_and_descends():
    devices = [
        {"inst_uuid": DEV_A, "model_id": "host"},
        {"inst_uuid": DEV_B, "model_id": "host"},
        {"inst_uuid": DEV_DIRECT, "model_id": "switch"},
    ]
    scope = SimpleNamespace(racks=[{"inst_uuid": RACK_A, "model_id": "rack"}], devices_by_rack_uuid={RACK_A: devices})
    room = {"inst_uuid": ROOM, "model_id": "server_room"}
    with (
        patch("apps.cmdb.services.room_screen_stats.resolve_room_rack_devices", return_value=scope),
        patch("apps.cmdb.services.room_screen_stats.InstanceManage.query_entity_by_uuid", return_value=room),
        patch("apps.cmdb.services.room_screen_stats.InstanceManage._has_topology_view_permission", return_value=True),
        patch(
            "apps.cmdb.services.model.ModelManage.search_model",
            return_value=[{"model_id": "host", "model_name": "主机"}, {"model_id": "switch", "model_name": "交换机"}],
        ),
    ):
        result = room_device_type_distribution(
            server_room_id=ROOM,
            permission_map={"10": {}},
            user=None,
            language="zh-Hans",
            parse_locator=_parse_locator,
        )
    assert result["data"] == [{"name": "主机", "value": 2}, {"name": "交换机", "value": 1}]


def _placed():
    rack = {"inst_uuid": RACK_A, "inst_name": "A01", "model_id": "rack"}
    other = {"inst_uuid": RACK_B, "inst_name": "A02", "model_id": "rack"}
    devices = [
        (rack, {"inst_uuid": DEV_A, "inst_name": "srv", "model_id": "host", "monitor_id": "mon-a", "rack_u_start": 1, "u_size": 2}),
        (rack, {"inst_uuid": DEV_B, "inst_name": "db", "model_id": "host", "monitor_id": "mon-b", "rack_u_start": 4, "u_size": 1}),
        (other, {"inst_uuid": DEV_DIRECT, "inst_name": "bare", "model_id": "switch", "monitor_id": "", "rack_u_start": None, "u_size": None}),
        (other, {"inst_uuid": OTHER, "inst_name": "ghost", "model_id": "host", "monitor_id": "mon-c", "rack_u_start": 1, "u_size": 1}),
    ]
    return devices


def _summary_response(items):
    return {"result": True, "data": {"items": items}, "message": ""}


@pytest.mark.unit
def test_alarm_coverage_level_rack_and_device_list_use_alarm_rows():
    placed = _placed()
    captured = []

    class Client:
        def query_active_alert_summaries_by_monitor_ids(self, monitor_ids, **kwargs):
            captured.append(list(monitor_ids))
            return _summary_response(
                [
                    {
                        "monitor_id": "mon-a",
                        "active_alarm_count": 3,
                        "highest_severity": "critical",
                        "level_counts": {"critical": 2, "error": 1, "warning": 0},
                    },
                    {
                        "monitor_id": "mon-b",
                        "active_alarm_count": 0,
                        "highest_severity": None,
                        "level_counts": {"critical": 0, "error": 0, "warning": 0},
                    },
                ]
            )

    with (
        patch("apps.cmdb.services.room_screen_stats._room_scope", return_value=(None, object())),
        patch("apps.cmdb.services.room_screen_stats._iter_room_devices", return_value=placed),
        patch("apps.cmdb.services.model.ModelManage.search_model", return_value=[{"model_id": "host", "model_name": "主机"}]),
    ):
        coverage = room_active_alarms(view="coverage", permission_map={"10": {}}, language="zh-Hans", monitor_client_factory=Client)
        levels = room_active_alarms(view="level_distribution", permission_map={"10": {}}, language="zh-Hans", monitor_client_factory=Client)
        racks = room_active_alarms(view="rack_top", limit=5, permission_map={"10": {}}, monitor_client_factory=Client)
        devices = room_active_alarms(view="device_list", limit=20, permission_map={"10": {}}, language="zh-Hans", monitor_client_factory=Client)

    assert coverage["data"] == [
        {"name": "已监控无告警", "value": 1},
        {"name": "已监控有告警", "value": 1},
        {"name": "未监控", "value": 1},
        {"name": "告警暂不可用", "value": 1},
    ]
    assert levels["data"] == [{"name": "严重", "value": 2}, {"name": "错误", "value": 1}]
    assert racks["data"] == [{"name": "A01", "value": 3}]
    assert devices["data"] == [
        {
            "device_name": "srv",
            "model_name": "主机",
            "rack_name": "A01",
            "u_position": "1-2",
            "highest_severity": "严重",
            "active_alarm_count": 3,
        }
    ]
    assert "content" not in devices["data"][0]
    assert captured[0] == ["mon-a", "mon-b", "mon-c"]


@pytest.mark.unit
def test_monitor_failure_degrades_only_coverage():
    placed = _placed()

    class Broken:
        def query_active_alert_summaries_by_monitor_ids(self, monitor_ids, **kwargs):
            return {"result": False, "data": {"items": []}, "message": "down"}

    with (
        patch("apps.cmdb.services.room_screen_stats._room_scope", return_value=(None, object())),
        patch("apps.cmdb.services.room_screen_stats._iter_room_devices", return_value=placed),
    ):
        coverage = room_active_alarms(view="coverage", permission_map={"10": {}}, language="zh-Hans", monitor_client_factory=Broken)
        levels = room_active_alarms(view="level_distribution", permission_map={"10": {}}, monitor_client_factory=Broken)
        racks = room_active_alarms(view="rack_top", permission_map={"10": {}}, monitor_client_factory=Broken)

    assert coverage["result"] is True
    assert {item["name"]: item["value"] for item in coverage["data"]}["告警暂不可用"] == 3
    assert {item["name"]: item["value"] for item in coverage["data"]}["未监控"] == 1
    assert levels["result"] is False
    assert levels["data"] == {}
    assert racks["result"] is False
    assert racks["data"] == {}


@pytest.mark.unit
def test_monitor_ids_are_batched_by_500():
    rack = {"inst_uuid": RACK_A, "inst_name": "A01"}
    placed = [
        (rack, {"inst_uuid": _uuid(index), "inst_name": f"d{index}", "model_id": "host", "monitor_id": f"mon-{index}"})
        for index in range(MONITOR_ID_BATCH_SIZE + 3)
    ]
    batches = []

    class Client:
        def query_active_alert_summaries_by_monitor_ids(self, monitor_ids, **kwargs):
            batches.append(list(monitor_ids))
            return _summary_response([])

    with (
        patch("apps.cmdb.services.room_screen_stats._room_scope", return_value=(None, object())),
        patch("apps.cmdb.services.room_screen_stats._iter_room_devices", return_value=placed),
    ):
        result = room_active_alarms(view="coverage", permission_map={"10": {}}, monitor_client_factory=Client)

    assert result["result"] is True
    assert [len(batch) for batch in batches] == [MONITOR_ID_BATCH_SIZE, 3]
