import json
from unittest.mock import MagicMock, patch

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.cmdb.services import rack_room

VIEWS = "apps.cmdb.views.instance"


def _uuid(value: int) -> str:
    return f"00000000-0000-4000-8000-{value:012d}"


def _assoc(src_model, dst_model, asst, ids):
    return {
        "src_model_id": src_model,
        "dst_model_id": dst_model,
        "model_asst_id": f"{src_model}_{asst}_{dst_model}",
        "asst_id": asst,
        "inst_list": [{"_id": i} for i in ids],
    }


@pytest.mark.unit
class TestGetRackLayout:
    @patch.object(rack_room.InstanceManage, "_has_topology_view_permission", return_value=True)
    @patch.object(rack_room.InstanceManage, "_query_instance_map_by_ids")
    @patch.object(rack_room.InstanceManage, "instance_association_instance_list")
    @patch.object(rack_room.InstanceManage, "query_entity_by_id")
    def test_assemble_devices(self, q_entity, q_assoc, q_map, _perm):
        q_entity.return_value = {"_id": 5, "inst_uuid": _uuid(5), "inst_name": "A03", "model_id": "rack", "u_count": 42}
        q_assoc.return_value = [_assoc("rack", "switch", "contains", [10])]
        q_map.return_value = {10: {"_id": 10, "inst_uuid": _uuid(10), "inst_name": "sw", "model_id": "switch", "rack_u_start": 41, "u_size": 2}}
        out = rack_room.get_rack_layout(5, permission_map={"x": 1}, user=None)
        assert out["rack"] == {"inst_uuid": _uuid(5), "inst_name": "A03", "u_count": 42}
        assert [d["inst_uuid"] for d in out["placed"]] == [_uuid(10)]


@pytest.mark.unit
class TestGetRoomLayout:
    @patch.object(rack_room.InstanceManage, "_has_topology_view_permission", return_value=True)
    @patch.object(rack_room.InstanceManage, "_query_instance_map_by_ids")
    @patch.object(rack_room.InstanceManage, "instance_association_instance_list")
    def test_assemble_racks_with_usage(self, q_assoc, q_map, _perm):
        def assoc_side_effect(model_id, inst_id):
            if model_id == "server_room":
                return [_assoc("server_room", "rack", "run", [5])]
            return [_assoc("rack", "switch", "contains", [10])]

        q_assoc.side_effect = assoc_side_effect

        def map_side_effect(ids):
            full = {
                5: {
                    "_id": 5,
                    "inst_uuid": _uuid(5),
                    "inst_name": "A03",
                    "model_id": "rack",
                    "row": 1,
                    "col": 1,
                    "location": "A01",
                    "u_count": 42,
                    "datacenter_type": "1",
                    "datacenter_state": "1",
                },
                10: {"_id": 10, "inst_name": "sw", "model_id": "switch", "rack_u_start": 1, "u_size": 21},
            }
            return {i: full[i] for i in ids if i in full}

        q_map.side_effect = map_side_effect

        out = rack_room.get_room_layout(7, permission_map={"x": 1}, user=None)
        assert len(out["racks"]) == 1
        # 占 U1-21 → 已用 21、利用率 50%、最大连续空闲 = U22-42 = 21
        assert out["racks"][0]["used_u"] == 21
        assert out["racks"][0]["usage"] == 50
        assert out["racks"][0]["max_free_u"] == 21

    @patch.object(rack_room.InstanceManage, "_has_topology_view_permission", return_value=True)
    @patch.object(rack_room.InstanceManage, "_query_instance_map_by_ids")
    @patch.object(rack_room.InstanceManage, "instance_association_instance_list")
    def test_room_position_uses_location_instead_of_legacy_row_col(self, q_assoc, q_map, _perm):
        # row/col 可能是历史残留属性，当前 rack 模型只维护 location；布局应以 location 为准。
        def assoc_side_effect(model_id, inst_id):
            if model_id == "server_room":
                return [_assoc("server_room", "rack", "run", [5])]
            return []

        q_assoc.side_effect = assoc_side_effect
        q_map.return_value = {
            5: {
                "_id": 5,
                "inst_uuid": _uuid(5),
                "inst_name": "ROOM3D-SHOT-RACK-C03",
                "model_id": "rack",
                "row": 3,
                "col": 3,
                "location": "A09",
                "u_count": 42,
            }
        }

        out = rack_room.get_room_layout(7, permission_map={"x": 1}, user=None)

        assert len(out["racks"]) == 1
        # A09：字母 A=列 1，数字 09=行 9（与俯视图「列字母 × 行数字」一致）
        assert out["racks"][0]["row"] == 9
        assert out["racks"][0]["col"] == 1
        assert out["racks"][0]["location"] == "A09"
        assert out["grid"] == {"max_row": 9, "max_col": 1}

    @patch.object(rack_room.InstanceManage, "_has_topology_view_permission", return_value=True)
    @patch.object(rack_room.InstanceManage, "_query_instance_map_by_ids")
    @patch.object(rack_room.InstanceManage, "instance_association_instance_list")
    def test_used_u_is_distinct_occupied_not_sum(self, q_assoc, q_map, _perm):
        # 一台落位 U1-2、一台未分配 U 位（有 u_size 无 rack_u_start）：
        # used_u 应为去重占用数 2（= u_count - free_u），不被未分配设备抬高，利用率不超 100%
        def assoc_side_effect(model_id, inst_id):
            if model_id == "server_room":
                return [_assoc("server_room", "rack", "run", [5])]
            return [_assoc("rack", "switch", "contains", [10, 11])]

        q_assoc.side_effect = assoc_side_effect

        def map_side_effect(ids):
            full = {
                5: {
                    "_id": 5,
                    "inst_uuid": _uuid(5),
                    "inst_name": "R",
                    "model_id": "rack",
                    "row": 1,
                    "col": 1,
                    "location": "A01",
                    "u_count": 10,
                    "datacenter_type": "1",
                },
                10: {"_id": 10, "inst_name": "sw1", "model_id": "switch", "rack_u_start": 1, "u_size": 2},
                11: {"_id": 11, "inst_name": "sw2", "model_id": "switch", "rack_u_start": None, "u_size": 2},
            }
            return {i: full[i] for i in ids if i in full}

        q_map.side_effect = map_side_effect

        out = rack_room.get_room_layout(7, permission_map={"x": 1}, user=None)
        rack = out["racks"][0]
        assert rack["used_u"] == 2  # 不是 2+2=4
        assert rack["free_u"] == 8
        assert rack["usage"] == 20

    @patch.object(rack_room.InstanceManage, "_has_topology_view_permission", return_value=False)
    @patch.object(rack_room.InstanceManage, "_query_instance_map_by_ids")
    @patch.object(rack_room.InstanceManage, "instance_association_instance_list")
    def test_denied_rack_is_pruned(self, q_assoc, q_map, _perm):
        # 无权限的机柜应被剔除，不出现在平面图，也不悬空
        q_assoc.return_value = [_assoc("server_room", "rack", "run", [5])]
        q_map.return_value = {
            5: {"_id": 5, "inst_name": "A03", "model_id": "rack", "row": 1, "col": 1, "u_count": 42, "datacenter_type": "1", "datacenter_state": "1"}
        }
        out = rack_room.get_room_layout(7, permission_map={"x": 1}, user=None)
        assert out["racks"] == []
        assert out["unplaced"] == []

    @patch.object(rack_room.InstanceManage, "_has_topology_view_permission", return_value=True)
    @patch.object(rack_room.InstanceManage, "_query_instance_map_by_ids")
    @patch.object(rack_room.InstanceManage, "instance_association_instance_list")
    def test_enum_list_value_is_scalarized(self, q_assoc, q_map, _perm):
        # CMDB 枚举以列表存储（单选也是 ['3']），需归一为标量供前端按枚举 id 着色
        def assoc_side_effect(model_id, inst_id):
            if model_id == "server_room":
                return [_assoc("server_room", "rack", "run", [5])]
            return []

        q_assoc.side_effect = assoc_side_effect
        q_map.return_value = {
            5: {
                "_id": 5,
                "inst_uuid": _uuid(5),
                "inst_name": "A03",
                "model_id": "rack",
                "row": 1,
                "col": 1,
                "location": "A01",
                "u_count": 42,
                "datacenter_type": ["3"],
                "datacenter_state": ["1"],
            }
        }
        out = rack_room.get_room_layout(7, permission_map={"x": 1}, user=None)
        assert out["racks"][0]["datacenter_type"] == "3"
        assert out["racks"][0]["datacenter_state"] == "1"


@pytest.mark.unit
class TestRackDevicePermission:
    @patch.object(rack_room.InstanceManage, "_has_topology_view_permission", return_value=False)
    @patch.object(rack_room.InstanceManage, "_query_instance_map_by_ids")
    @patch.object(rack_room.InstanceManage, "instance_association_instance_list")
    @patch.object(rack_room.InstanceManage, "query_entity_by_id")
    def test_denied_device_is_pruned(self, q_entity, q_assoc, q_map, _perm):
        q_entity.return_value = {"_id": 5, "inst_name": "A03", "model_id": "rack", "u_count": 42}
        q_assoc.return_value = [_assoc("rack", "switch", "contains", [10])]
        q_map.return_value = {10: {"_id": 10, "inst_name": "sw", "model_id": "switch", "rack_u_start": 41, "u_size": 2}}
        out = rack_room.get_rack_layout(5, permission_map={"x": 1}, user=None)
        assert out["placed"] == []
        assert out["unplaced"] == []


@pytest.mark.unit
class TestRoom3DRackDeviceSummaries:
    @patch.object(rack_room.InstanceManage, "_has_topology_view_permission")
    @patch.object(rack_room.InstanceManage, "query_entity_by_uuids")
    @patch.object(rack_room.InstanceManage, "query_entity_by_ids")
    def test_batches_associations_instances_and_permissions(self, q_racks, q_devices, q_perm):
        rack_5_uuid = "550e8400-e29b-41d4-a716-446655440005"
        rack_6_uuid = "550e8400-e29b-41d4-a716-446655440006"
        device_10_uuid = "550e8400-e29b-41d4-a716-446655440010"
        device_11_uuid = "550e8400-e29b-41d4-a716-446655440011"
        device_12_uuid = "550e8400-e29b-41d4-a716-446655440012"
        graph_client = MagicMock()
        graph_client.query_edge.return_value = [
            {"src_inst_uuid": rack_5_uuid, "dst_inst_uuid": device_10_uuid},
            {"src_inst_uuid": rack_5_uuid, "dst_inst_uuid": device_11_uuid},
            {"src_inst_uuid": rack_6_uuid, "dst_inst_uuid": device_12_uuid},
        ]
        graph_context = MagicMock()
        graph_context.__enter__.return_value = graph_client
        graph_context.__exit__.return_value = False
        q_racks.return_value = [
            {"_id": 5, "inst_uuid": rack_5_uuid, "model_id": "rack"},
            {"_id": 6, "inst_uuid": rack_6_uuid, "model_id": "rack"},
        ]
        device_rows = [
            {
                "_id": 10,
                "inst_uuid": device_10_uuid,
                "inst_name": "sw",
                "model_id": "switch",
                "rack_u_start": 1,
                "u_size": 2,
                "status": ["running"],
            },
            {
                "_id": 11,
                "inst_uuid": device_11_uuid,
                "inst_name": "host",
                "model_id": "host",
                "rack_u_start": None,
                "u_size": 1,
            },
            {
                "_id": 12,
                "inst_uuid": device_12_uuid,
                "inst_name": "db",
                "model_id": "host",
                "rack_u_start": 3,
                "u_size": 2,
            },
        ]
        q_devices.side_effect = [q_racks.return_value, device_rows]
        q_perm.side_effect = lambda inst, *a, **k: inst["_id"] != 12

        with patch("apps.cmdb.services.rack_room.GraphClient", return_value=graph_context):
            out = rack_room.get_room3d_rack_device_summaries(
                [rack_5_uuid, rack_6_uuid],
                permission_map={"x": 1},
                user=None,
            )

        assert out == {
            rack_5_uuid: {
                "devices": [
                    {
                        "device_id": device_10_uuid,
                        "device_name": "sw",
                        "model_id": "switch",
                        "rack_u_start": 1,
                        "u_size": 2,
                        "status": "running",
                    }
                ],
                "device_count": 2,
                "unplaced_device_count": 1,
            },
            rack_6_uuid: {"devices": [], "device_count": 0, "unplaced_device_count": 0},
        }
        q_racks.assert_called_once_with([5, 6])
        assert q_devices.call_args_list[0].args == ([rack_5_uuid, rack_6_uuid],)
        assert q_devices.call_args_list[1].args == ([device_10_uuid, device_11_uuid, device_12_uuid],)
        graph_client.query_edge.assert_called_once_with(
            "instance_association",
            [
                {"field": "src_inst_uuid", "type": "str[]", "value": [rack_5_uuid, rack_6_uuid]},
                {"field": "src_model_id", "type": "str=", "value": "rack"},
            ],
        )

    @patch.object(rack_room.InstanceManage, "_has_topology_view_permission", return_value=True)
    @patch.object(rack_room.InstanceManage, "query_entity_by_uuids")
    @patch.object(rack_room.InstanceManage, "query_entity_by_ids")
    def test_uses_outgoing_rack_relations_only(self, q_racks, q_devices, _perm):
        rack_uuid = "550e8400-e29b-41d4-a716-446655440005"
        other_rack_uuid = "550e8400-e29b-41d4-a716-446655440999"
        device_uuid = "550e8400-e29b-41d4-a716-446655440010"
        other_device_uuid = "550e8400-e29b-41d4-a716-446655440011"
        graph_client = MagicMock()
        graph_client.query_edge.return_value = [
            {"src_inst_uuid": rack_uuid, "dst_inst_uuid": device_uuid},
            {"src_inst_uuid": other_rack_uuid, "dst_inst_uuid": other_device_uuid},
        ]
        graph_context = MagicMock()
        graph_context.__enter__.return_value = graph_client
        graph_context.__exit__.return_value = False
        q_racks.return_value = [{"_id": 5, "inst_uuid": rack_uuid, "model_id": "rack"}]
        device_rows = [
            {
                "_id": 10,
                "inst_uuid": device_uuid,
                "inst_name": "sw",
                "model_id": "switch",
                "rack_u_start": 1,
                "u_size": 1,
            },
            {
                "_id": 11,
                "inst_uuid": other_device_uuid,
                "inst_name": "other",
                "model_id": "switch",
                "rack_u_start": 2,
                "u_size": 1,
            },
        ]

        q_devices.side_effect = [q_racks.return_value, device_rows]
        with patch("apps.cmdb.services.rack_room.GraphClient", return_value=graph_context):
            out = rack_room.get_room3d_rack_device_summaries([rack_uuid], permission_map={"x": 1})

        assert out[rack_uuid]["device_count"] == 1
        q_racks.assert_called_once_with([5])
        assert q_devices.call_args_list[0].args == ([rack_uuid],)
        assert q_devices.call_args_list[1].args == ([device_uuid, other_device_uuid],)
        graph_client.query_edge.assert_called_once_with(
            "instance_association",
            [
                {"field": "src_inst_uuid", "type": "str[]", "value": [rack_uuid]},
                {"field": "src_model_id", "type": "str=", "value": "rack"},
            ],
        )

    @patch.object(rack_room.InstanceManage, "_has_topology_view_permission", return_value=True)
    @patch.object(rack_room.InstanceManage, "query_entity_by_uuids")
    @patch.object(rack_room.InstanceManage, "query_entity_by_ids")
    def test_summary_skips_device_without_uuid(self, q_racks, q_devices, _perm):
        rack_uuid = "550e8400-e29b-41d4-a716-446655440005"
        graph_client = MagicMock()
        graph_client.query_edge.return_value = [{"src_inst_uuid": rack_uuid, "dst_inst_uuid": "550e8400-e29b-41d4-a716-446655440010"}]
        graph_context = MagicMock()
        graph_context.__enter__.return_value = graph_client
        graph_context.__exit__.return_value = False
        q_racks.return_value = [{"_id": 5, "inst_uuid": rack_uuid, "model_id": "rack"}]
        q_devices.side_effect = [
            q_racks.return_value,
            [{"_id": 10, "model_id": "switch", "rack_u_start": 1, "u_size": 1}],
        ]

        with patch("apps.cmdb.services.rack_room.GraphClient", return_value=graph_context):
            out = rack_room.get_room3d_rack_device_summaries([rack_uuid], permission_map={"x": 1})

        assert out[rack_uuid] == {
            "devices": [],
            "device_count": 0,
            "unplaced_device_count": 0,
        }


# ---------------------------------------------------------------------------
# room_layout / rack_layout view actions
# ---------------------------------------------------------------------------


def _body(response):
    if hasattr(response, "render"):
        response.render()
        return json.loads(response.rendered_content)
    return json.loads(response.content)


def _get_req(user):
    factory = APIRequestFactory()
    request = factory.get("/x/")
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=user)
    return request


@pytest.fixture
def superuser(authenticated_user):
    u = authenticated_user
    u.is_superuser = True
    u.group_list = [{"id": 1}]
    u.group_tree = []
    u.roles = ["admin"]
    return u


@pytest.fixture(autouse=True)
def _layout_perm(monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.CmdbRulesFormatUtil.format_user_groups_permissions",
        lambda request, model_id="", permission_type=None: {1: {"permission_instances_map": {}, "inst_names": []}},
    )
    monkeypatch.setattr(
        f"{VIEWS}.InstanceViewSet.require_instance_permission",
        lambda self, request, instance, operator=None: None,
    )


@pytest.mark.unit
@pytest.mark.django_db
class TestLayoutViews:
    def test_rack_layout_route(self, superuser, monkeypatch):
        from apps.cmdb.views.instance import InstanceViewSet

        sample_uuid = "550e8400-e29b-41d4-a716-446655440005"
        monkeypatch.setattr(
            f"{VIEWS}.InstanceManage.query_entity_by_uuid",
            lambda uid: {"_id": 5, "model_id": "rack", "inst_name": "A03", "inst_uuid": uid},
        )
        monkeypatch.setattr(f"{VIEWS}.get_rack_layout", lambda *a, **k: {"ok": 1})
        response = InstanceViewSet.as_view({"get": "rack_layout"})(_get_req(superuser), model_id="rack", inst_uuid=sample_uuid)
        assert response.status_code == status.HTTP_200_OK
        assert _body(response)["data"] == {"ok": 1}

    def test_room_layout_route(self, superuser, monkeypatch):
        from apps.cmdb.views.instance import InstanceViewSet

        sample_uuid = "550e8400-e29b-41d4-a716-446655440007"
        monkeypatch.setattr(
            f"{VIEWS}.InstanceManage.query_entity_by_uuid",
            lambda uid: {"_id": 7, "model_id": "server_room", "inst_name": "R1", "inst_uuid": uid},
        )
        monkeypatch.setattr(f"{VIEWS}.get_room_layout", lambda *a, **k: {"racks": []})
        response = InstanceViewSet.as_view({"get": "room_layout"})(_get_req(superuser), model_id="server_room", inst_uuid=sample_uuid)
        assert response.status_code == status.HTTP_200_OK
        assert _body(response)["data"] == {"racks": []}

    def test_rack_layout_404_when_missing(self, superuser, monkeypatch):
        from apps.cmdb.views.instance import InstanceViewSet

        monkeypatch.setattr(f"{VIEWS}.InstanceManage.query_entity_by_uuid", lambda uid: None)
        monkeypatch.setattr(f"{VIEWS}.get_rack_layout", lambda *a, **k: {"ok": 1})
        response = InstanceViewSet.as_view({"get": "rack_layout"})(
            _get_req(superuser),
            model_id="rack",
            inst_uuid="550e8400-e29b-41d4-a716-446655440099",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert _body(response)["message"] == "实例不存在"


@pytest.mark.unit
class TestRacksGroupedByRoomView:
    def test_passes_search_and_page(self, monkeypatch):
        from apps.cmdb.views.instance import InstanceViewSet

        captured = {}

        def fake_list(**kwargs):
            captured.update(kwargs)
            return {"groups": [{"room_uuid": _uuid(1), "room_name": "北京-1F", "racks": []}], "count": 1}

        monkeypatch.setattr(f"{VIEWS}.list_racks_grouped_by_room", fake_list)
        monkeypatch.setattr(
            f"{VIEWS}.CmdbRulesFormatUtil.format_user_groups_permissions",
            lambda request, model_id="", permission_type=None: {model_id: {}},
        )
        request = MagicMock()
        request.query_params = {"page": "2", "page_size": "10", "search": "北京"}
        request.user.username = "alice"
        response = InstanceViewSet().racks_grouped_by_room(request)
        assert response.status_code == status.HTTP_200_OK
        assert _body(response)["data"]["count"] == 1
        assert captured["page"] == 2
        assert captured["page_size"] == 10
        assert captured["search"] == "北京"
        assert captured["creator"] == "alice"

    def test_rejects_unbounded_page_size(self, monkeypatch):
        from apps.cmdb.views.instance import InstanceViewSet

        monkeypatch.setattr(f"{VIEWS}.list_racks_grouped_by_room", lambda **kwargs: {"groups": [], "count": 0})
        request = MagicMock()
        request.query_params = {"page_size": "101"}
        request.user.username = "alice"
        response = InstanceViewSet().racks_grouped_by_room(request)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "page_size" in _body(response)["message"]


@pytest.mark.unit
class TestListServerRooms:
    """list_server_rooms：运维分析 dynamic 模式选项源用的"所有机房列表"。

    验证：
    1. 走 ``InstanceManage.instance_list`` 现成的权限过滤
    2. 直接返回 cmdb 原始字段（_id, inst_name, ...）不做重命名
    3. 业务上限 page_size=1000
    4. 排序按 inst_name
    """

    @patch.object(rack_room.InstanceManage, "instance_list")
    def test_returns_raw_cmdb_fields(self, mock_instance_list):
        """应原样返回 cmdb 实例字段，不做 _id→id 等重命名。"""
        mock_instance_list.return_value = (
            [
                {
                    "_id": 1,
                    "inst_name": "机房A",
                    "model_id": "server_room",
                    "organization": [10],
                },
                {
                    "_id": 2,
                    "inst_name": "机房B",
                    "model_id": "server_room",
                    "organization": [20],
                },
            ],
            2,
        )
        result = rack_room.list_server_rooms(permission_map={}, user_info=None)
        assert result == [
            {"_id": 1, "inst_name": "机房A", "model_id": "server_room", "organization": [10]},
            {"_id": 2, "inst_name": "机房B", "model_id": "server_room", "organization": [20]},
        ]

    @patch.object(rack_room.InstanceManage, "instance_list")
    def test_passes_permission_map_to_instance_list(self, mock_instance_list):
        """permission_map 应透传给 InstanceManage.instance_list 以走现成权限过滤。"""
        mock_instance_list.return_value = ([], 0)
        perm = {"10": {"inst_names": ["机房A"], "instance_permission": {}}}
        rack_room.list_server_rooms(permission_map=perm, user_info=None)
        kwargs = mock_instance_list.call_args.kwargs
        assert kwargs["model_id"] == "server_room"
        assert kwargs["permission_map"] == perm
        assert kwargs["page"] == 1
        assert kwargs["page_size"] == 1000  # 业务上限
        assert kwargs["order"] == "inst_name"

    @patch.object(rack_room.InstanceManage, "instance_list")
    def test_default_empty_permission_map(self, mock_instance_list):
        """未传 permission_map 时默认为空 dict（不阻断调用）。"""
        mock_instance_list.return_value = ([], 0)
        rack_room.list_server_rooms()
        kwargs = mock_instance_list.call_args.kwargs
        assert kwargs["permission_map"] == {}

    @patch.object(rack_room.InstanceManage, "instance_list")
    def test_handles_empty_list(self, mock_instance_list):
        """无机房时返回空列表（不返回 None）。"""
        mock_instance_list.return_value = ([], 0)
        assert rack_room.list_server_rooms(permission_map={}) == []
        mock_instance_list.return_value = (None, 0)
        assert rack_room.list_server_rooms(permission_map={}) == []


@pytest.mark.unit
class TestGetRoomListNatsHandler:
    """NATS handler ``get_room_list`` 应：
    1. 返回 ``{"items": [...]}`` 信封
    2. 走 ``_build_nats_permission_map`` 构造 permission_map 并透传给 list_server_rooms
    """

    @patch("apps.cmdb.nats.nats.rack_room.list_server_rooms")
    @patch("apps.cmdb.nats.nats._build_nats_permission_map", return_value={"10": {}})
    def test_returns_items_envelope(self, mock_perm_map, mock_list_rooms):
        from apps.cmdb.nats import nats

        mock_list_rooms.return_value = [
            {
                "_id": 1,
                "inst_uuid": "11111111-1111-4111-8111-111111111111",
                "inst_name": "机房A",
                "model_id": "server_room",
            },
        ]
        result = nats.get_room_list(user_info={"team": 1, "user": "alice"})
        assert result == {
            "items": [
                {
                    "_id": 1,
                    "inst_uuid": "11111111-1111-4111-8111-111111111111",
                    "inst_name": "机房A",
                    "model_id": "server_room",
                }
            ]
        }

    @patch("apps.cmdb.nats.nats.rack_room.list_server_rooms")
    @patch("apps.cmdb.nats.nats._build_nats_permission_map", return_value={"10": {}})
    def test_passes_permission_map_to_list_server_rooms(self, mock_perm_map, mock_list_rooms):
        from apps.cmdb.nats import nats

        mock_list_rooms.return_value = []
        nats.get_room_list(user_info={"team": 1, "user": "alice"})
        kwargs = mock_list_rooms.call_args.kwargs
        assert kwargs["permission_map"] == {"10": {}}
        assert kwargs["user_info"] == {"team": 1, "user": "alice"}

    @patch("apps.cmdb.nats.nats.rack_room.list_server_rooms")
    @patch("apps.cmdb.nats.nats._build_nats_permission_map", return_value=None)
    def test_handles_none_permission_map(self, mock_perm_map, mock_list_rooms):
        """_build_nats_permission_map 返回 None 时不阻断（list_server_rooms 内部兜底空 dict）。"""
        from apps.cmdb.nats import nats

        mock_list_rooms.return_value = []
        nats.get_room_list(user_info={"team": 1})
        kwargs = mock_list_rooms.call_args.kwargs
        assert kwargs["permission_map"] == {}


@pytest.mark.unit
class TestListRacksGroupedByRoom:
    """机柜选择器：按机房分组，搜索命中机房名或机柜名。"""

    def _rooms(self):
        return [
            {"inst_uuid": _uuid(1), "inst_name": "北京-1F", "model_id": "server_room"},
            {"inst_uuid": _uuid(2), "inst_name": "上海-2F", "model_id": "server_room"},
        ]

    def _racks(self):
        return {
            _uuid(11): {"inst_uuid": _uuid(11), "inst_name": "A01", "model_id": "rack"},
            _uuid(12): {"inst_uuid": _uuid(12), "inst_name": "A02", "model_id": "rack"},
            _uuid(21): {"inst_uuid": _uuid(21), "inst_name": "B01", "model_id": "rack"},
            _uuid(99): {"inst_uuid": _uuid(99), "inst_name": "Z99", "model_id": "rack"},
        }

    def _patch_graph(self, monkeypatch, *, permission_ok=True):
        rooms = self._rooms()
        racks = self._racks()
        room_to_racks = {
            _uuid(1): [_uuid(11), _uuid(12)],
            _uuid(2): [_uuid(21)],
        }
        rack_to_rooms = {
            _uuid(11): [_uuid(1)],
            _uuid(12): [_uuid(1)],
            _uuid(21): [_uuid(2)],
            _uuid(99): [],
        }

        def instance_list(model_id, params, page, page_size, order, permission_map, creator=None, case_sensitive=True):
            keyword = ""
            for item in params or []:
                if item.get("field") == "inst_name":
                    keyword = str(item.get("value") or "")
                    break
            if model_id == "server_room":
                items = rooms
            else:
                items = list(racks.values())
            if keyword:
                items = [item for item in items if keyword.lower() in str(item.get("inst_name") or "").lower()]
            start = (page - 1) * page_size
            return items[start : start + page_size], len(items)

        def association_map(model_id, inst_uuids, related_model=None):
            mapping = room_to_racks if model_id == "server_room" else rack_to_rooms
            return {uid: list(mapping.get(uid, [])) for uid in inst_uuids}

        def query_by_uuids(inst_uuids):
            catalog = {**{item["inst_uuid"]: item for item in rooms}, **racks}
            return [catalog[uid] for uid in inst_uuids if uid in catalog]

        monkeypatch.setattr(rack_room.InstanceManage, "instance_list", instance_list)
        monkeypatch.setattr(rack_room.InstanceManage, "instance_association_map_by_uuids", association_map)
        monkeypatch.setattr(rack_room.InstanceManage, "query_entity_by_uuids", query_by_uuids)
        monkeypatch.setattr(
            rack_room.InstanceManage,
            "_has_topology_view_permission",
            lambda instance, permission_map, user=None: permission_ok if permission_ok is True else permission_ok(instance),
        )

    def test_groups_racks_under_visible_rooms(self, monkeypatch):
        self._patch_graph(monkeypatch)
        out = rack_room.list_racks_grouped_by_room(page=1, page_size=20)
        assert out["count"] == 2
        assert [group["room_name"] for group in out["groups"]] == ["北京-1F", "上海-2F"]
        assert [rack["inst_name"] for rack in out["groups"][0]["racks"]] == ["A01", "A02"]
        assert [rack["inst_name"] for rack in out["groups"][1]["racks"]] == ["B01"]

    def test_paginates_by_room_not_rack(self, monkeypatch):
        self._patch_graph(monkeypatch)
        out = rack_room.list_racks_grouped_by_room(page=1, page_size=1)
        assert out["count"] == 2
        assert len(out["groups"]) == 1
        assert out["groups"][0]["room_name"] == "北京-1F"
        assert [rack["inst_name"] for rack in out["groups"][0]["racks"]] == ["A01", "A02"]

    def test_search_by_room_name_returns_all_racks_in_room(self, monkeypatch):
        self._patch_graph(monkeypatch)
        out = rack_room.list_racks_grouped_by_room(search="北京", page=1, page_size=20)
        assert out["count"] == 1
        assert out["groups"][0]["room_name"] == "北京-1F"
        assert [rack["inst_name"] for rack in out["groups"][0]["racks"]] == ["A01", "A02"]

    def test_search_by_rack_name_keeps_parent_room_group(self, monkeypatch):
        self._patch_graph(monkeypatch)
        out = rack_room.list_racks_grouped_by_room(search="A01", page=1, page_size=20)
        assert out["count"] == 1
        assert out["groups"][0]["room_name"] == "北京-1F"
        assert out["groups"][0]["room_uuid"] == _uuid(1)
        names = [rack["inst_name"] for rack in out["groups"][0]["racks"]]
        assert "A01" in names

    def test_unassociated_rack_search_uses_null_room(self, monkeypatch):
        self._patch_graph(monkeypatch)
        out = rack_room.list_racks_grouped_by_room(search="Z99", page=1, page_size=20)
        assert out["count"] == 1
        assert out["groups"][0]["room_uuid"] is None
        assert [rack["inst_name"] for rack in out["groups"][0]["racks"]] == ["Z99"]

    def test_hides_racks_without_view_permission(self, monkeypatch):
        self._patch_graph(
            monkeypatch,
            permission_ok=lambda instance: instance.get("inst_name") != "A02",
        )
        out = rack_room.list_racks_grouped_by_room(page=1, page_size=20)
        assert [rack["inst_name"] for rack in out["groups"][0]["racks"]] == ["A01"]

    def test_rejects_unbounded_page_size(self, monkeypatch):
        self._patch_graph(monkeypatch)
        with pytest.raises(ValueError, match="page_size"):
            rack_room.list_racks_grouped_by_room(page=1, page_size=101)
