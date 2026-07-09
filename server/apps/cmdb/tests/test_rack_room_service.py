import json
from unittest.mock import MagicMock, patch

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.cmdb.services import rack_room

VIEWS = "apps.cmdb.views.instance"


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
        q_entity.return_value = {"_id": 5, "inst_name": "A03", "model_id": "rack", "u_count": 42}
        q_assoc.return_value = [_assoc("rack", "switch", "contains", [10])]
        q_map.return_value = {10: {"_id": 10, "inst_name": "sw", "model_id": "switch", "rack_u_start": 41, "u_size": 2}}
        out = rack_room.get_rack_layout(5, permission_map={"x": 1}, user=None)
        assert out["rack"] == {"inst_id": "5", "inst_name": "A03", "u_count": 42}
        assert [d["inst_id"] for d in out["placed"]] == ["10"]


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
        assert out["racks"][0]["row"] == 1
        assert out["racks"][0]["col"] == 9
        assert out["racks"][0]["location"] == "A09"
        assert out["grid"] == {"max_row": 1, "max_col": 9}

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
                5: {"_id": 5, "inst_name": "R", "model_id": "rack", "row": 1, "col": 1, "location": "A01", "u_count": 10, "datacenter_type": "1"},
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
    @patch.object(rack_room.InstanceManage, "_query_instance_map_by_ids")
    def test_batches_associations_instances_and_permissions(self, q_map, q_perm):
        graph_client = MagicMock()
        graph_client.query_edge.return_value = [
            {"src_inst_id": 5, "dst_inst_id": 10},
            {"src_inst_id": 5, "dst_inst_id": 11},
            {"src_inst_id": 6, "dst_inst_id": 12},
        ]
        graph_context = MagicMock()
        graph_context.__enter__.return_value = graph_client
        graph_context.__exit__.return_value = False
        q_map.return_value = {
            10: {
                "_id": 10,
                "inst_name": "sw",
                "model_id": "switch",
                "rack_u_start": 1,
                "u_size": 2,
                "status": ["running"],
            },
            11: {
                "_id": 11,
                "inst_name": "host",
                "model_id": "host",
                "rack_u_start": None,
                "u_size": 1,
            },
            12: {
                "_id": 12,
                "inst_name": "db",
                "model_id": "host",
                "rack_u_start": 3,
                "u_size": 2,
            },
        }
        q_perm.side_effect = lambda inst, *a, **k: inst["_id"] != 12

        with patch("apps.cmdb.services.rack_room.GraphClient", return_value=graph_context):
            out = rack_room.get_room3d_rack_device_summaries(
                [5, "6", 5, "", None],
                permission_map={"x": 1},
                user=None,
            )

        assert out == {
            5: {
                "devices": [
                    {
                        "device_id": "10",
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
            6: {"devices": [], "device_count": 0, "unplaced_device_count": 0},
        }
        q_map.assert_called_once_with({10, 11, 12})
        graph_client.query_edge.assert_called_once_with(
            "instance_association",
            [
                {"field": "src_inst_id", "type": "int[]", "value": [5, 6]},
                {"field": "src_model_id", "type": "str=", "value": "rack"},
            ],
        )

    @patch.object(rack_room.InstanceManage, "_has_topology_view_permission", return_value=True)
    @patch.object(rack_room.InstanceManage, "_query_instance_map_by_ids")
    def test_uses_outgoing_rack_relations_only(self, q_map, _perm):
        graph_client = MagicMock()
        graph_client.query_edge.return_value = [
            {"src_inst_id": 5, "dst_inst_id": 10},
            {"src_inst_id": 999, "dst_inst_id": 11},
        ]
        graph_context = MagicMock()
        graph_context.__enter__.return_value = graph_client
        graph_context.__exit__.return_value = False
        q_map.return_value = {
            10: {
                "_id": 10,
                "inst_name": "sw",
                "model_id": "switch",
                "rack_u_start": 1,
                "u_size": 1,
            }
        }

        with patch("apps.cmdb.services.rack_room.GraphClient", return_value=graph_context):
            out = rack_room.get_room3d_rack_device_summaries([5], permission_map={"x": 1})

        assert out[5]["device_count"] == 1
        q_map.assert_called_once_with({10})
        graph_client.query_edge.assert_called_once_with(
            "instance_association",
            [
                {"field": "src_inst_id", "type": "int[]", "value": [5]},
                {"field": "src_model_id", "type": "str=", "value": "rack"},
            ],
        )


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

        monkeypatch.setattr(
            f"{VIEWS}.InstanceManage.query_entity_by_id",
            lambda pk: {"_id": 5, "model_id": "rack", "inst_name": "A03"},
        )
        monkeypatch.setattr(f"{VIEWS}.get_rack_layout", lambda *a, **k: {"ok": 1})
        response = InstanceViewSet.as_view({"get": "rack_layout"})(_get_req(superuser), model_id="rack", inst_id="5")
        assert response.status_code == status.HTTP_200_OK
        assert _body(response)["data"] == {"ok": 1}

    def test_room_layout_route(self, superuser, monkeypatch):
        from apps.cmdb.views.instance import InstanceViewSet

        monkeypatch.setattr(
            f"{VIEWS}.InstanceManage.query_entity_by_id",
            lambda pk: {"_id": 7, "model_id": "server_room", "inst_name": "R1"},
        )
        monkeypatch.setattr(f"{VIEWS}.get_room_layout", lambda *a, **k: {"racks": []})
        response = InstanceViewSet.as_view({"get": "room_layout"})(_get_req(superuser), model_id="server_room", inst_id="7")
        assert response.status_code == status.HTTP_200_OK
        assert _body(response)["data"] == {"racks": []}

    def test_rack_layout_404_when_missing(self, superuser, monkeypatch):
        from apps.cmdb.views.instance import InstanceViewSet

        monkeypatch.setattr(f"{VIEWS}.InstanceManage.query_entity_by_id", lambda pk: None)
        monkeypatch.setattr(f"{VIEWS}.get_rack_layout", lambda *a, **k: {"ok": 1})
        response = InstanceViewSet.as_view({"get": "rack_layout"})(_get_req(superuser), model_id="rack", inst_id="999")
        assert response.status_code == status.HTTP_404_NOT_FOUND
