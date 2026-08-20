from unittest.mock import MagicMock, patch

import pytest

from apps.cmdb.services.instance import InstanceManage


def _rows():
    # 两条链路指向同一对端 456 与另一对端 789；含一条重复 rel_id=11 用于验证去重
    return [
        {
            "dev_id": 123,
            "dev_name": "sw-core",
            "dev_model": "switch",
            "local_if": "Gi0/1",
            "peer_if": "Eth1/1",
            "peer_id": 456,
            "peer_name": "sw-a",
            "peer_model": "switch",
            "rel_id": 11,
        },
        {
            "dev_id": 123,
            "dev_name": "sw-core",
            "dev_model": "switch",
            "local_if": "Gi0/1",
            "peer_if": "Eth1/1",
            "peer_id": 456,
            "peer_name": "sw-a",
            "peer_model": "switch",
            "rel_id": 11,
        },
        {
            "dev_id": 123,
            "dev_name": "sw-core",
            "dev_model": "switch",
            "local_if": "Gi0/2",
            "peer_if": "Eth2/2",
            "peer_id": 789,
            "peer_name": "sw-b",
            "peer_model": "switch",
            "rel_id": 12,
        },
    ]


@pytest.mark.unit
class TestNetworkTopologyService:
    @patch("apps.cmdb.services.instance.GraphClient")
    def test_assemble_nodes_links_and_dedup(self, mock_gc):
        ag = MagicMock()
        ag.query_network_topo.return_value = _rows()
        mock_gc.return_value.__enter__.return_value = ag

        # 默认 depth=1：只展开中心一跳
        result = InstanceManage.network_topology(123, "switch", permission_map=None, user=None)

        center = result["center"]
        assert center["id"] == "123"
        assert center["name"] == "sw-core"
        assert center["model_id"] == "switch"
        assert center["hop"] == 0
        assert center["expanded"] is True
        assert result["truncated"] is False
        assert {n["id"] for n in result["nodes"]} == {"123", "456", "789"}
        # 一跳邻居 hop=1 且尚未展开
        peer = next(n for n in result["nodes"] if n["id"] == "456")
        assert peer["hop"] == 1
        assert peer["expanded"] is False
        # rel_id=11 去重后只剩 2 条
        assert len(result["links"]) == 2
        link = next(item for item in result["links"] if item["target_device"] == "456")
        assert link["source_inst_name"] == "Gi0/1"
        assert link["target_inst_name"] == "Eth1/1"
        assert link["source_device"] == "123"

    @patch("apps.cmdb.services.instance.InstanceManage.query_entity_by_id")
    @patch("apps.cmdb.services.instance.GraphClient")
    def test_empty_topo_returns_center_only(self, mock_gc, mock_qbi):
        ag = MagicMock()
        ag.query_network_topo.return_value = []
        mock_gc.return_value.__enter__.return_value = ag
        mock_qbi.return_value = {"_id": 123, "inst_name": "sw-core", "model_id": "switch"}

        result = InstanceManage.network_topology(123, "switch", permission_map=None, user=None)
        assert result["center"]["id"] == "123"
        assert result["center"]["name"] == "sw-core"
        assert [n["id"] for n in result["nodes"]] == ["123"]
        assert result["links"] == []
        assert result["truncated"] is False

    @patch("apps.cmdb.services.instance.InstanceManage._has_topology_view_permission")
    @patch("apps.cmdb.services.instance.InstanceManage._query_instance_map_by_ids")
    @patch("apps.cmdb.services.instance.GraphClient")
    def test_permission_filters_invisible_peer(self, mock_gc, mock_map, mock_perm):
        ag = MagicMock()
        ag.query_network_topo.return_value = _rows()
        mock_gc.return_value.__enter__.return_value = ag
        mock_map.return_value = {456: {"_id": 456}, 789: {"_id": 789}}
        # 456 可见、789 不可见
        mock_perm.side_effect = lambda inst, pm, user=None: inst and inst.get("_id") == 456

        result = InstanceManage.network_topology(123, "switch", permission_map={"1": {"inst_names": []}}, user=None)
        assert {n["id"] for n in result["nodes"]} == {"123", "456"}
        assert all(item["target_device"] != "789" for item in result["links"])

    @patch("apps.cmdb.services.instance.GraphClient")
    def test_depth_two_expands_second_hop(self, mock_gc):
        # 中心 123 -> 456；456 -> 999（第二跳）
        def _topo(dev_id, belong):
            if int(dev_id) == 123:
                return [
                    {
                        "dev_id": 123,
                        "dev_name": "sw-core",
                        "dev_model": "switch",
                        "local_if": "Gi0/1",
                        "peer_if": "Eth1/1",
                        "peer_id": 456,
                        "peer_name": "sw-a",
                        "peer_model": "switch",
                        "rel_id": 11,
                    }
                ]
            if int(dev_id) == 456:
                return [
                    {
                        "dev_id": 456,
                        "dev_name": "sw-a",
                        "dev_model": "switch",
                        "local_if": "Eth1/2",
                        "peer_if": "Te0/1",
                        "peer_id": 999,
                        "peer_name": "sw-leaf",
                        "peer_model": "switch",
                        "rel_id": 22,
                    }
                ]
            return []

        ag = MagicMock()
        ag.query_network_topo.side_effect = _topo
        mock_gc.return_value.__enter__.return_value = ag

        result = InstanceManage.network_topology(123, "switch", depth=2, permission_map=None, user=None)

        nodes = {n["id"]: n for n in result["nodes"]}
        assert set(nodes) == {"123", "456", "999"}
        assert nodes["123"]["hop"] == 0 and nodes["123"]["expanded"] is True
        assert nodes["456"]["hop"] == 1 and nodes["456"]["expanded"] is True
        # 第二跳节点已发现但其邻居未再展开
        assert nodes["999"]["hop"] == 2 and nodes["999"]["expanded"] is False
        assert {item["relationship_id"] for item in result["links"]} == {"11", "22"}
        assert result["truncated"] is False

    @patch("apps.cmdb.services.instance.InstanceManage._has_topology_view_permission")
    @patch("apps.cmdb.services.instance.InstanceManage._query_instance_map_by_ids")
    @patch("apps.cmdb.services.instance.GraphClient")
    def test_permission_prunes_through_unauthorized_middle(self, mock_gc, mock_map, mock_perm):
        # 链路 123 -> 456(无权限) -> 999(有权限)：剪枝后 456 不出现，且 999 不应被查询/变成孤点
        def _topo(dev_id, belong):
            if int(dev_id) == 123:
                return [
                    {
                        "dev_id": 123,
                        "dev_name": "sw-core",
                        "dev_model": "switch",
                        "local_if": "Gi0/1",
                        "peer_if": "Eth1/1",
                        "peer_id": 456,
                        "peer_name": "sw-mid",
                        "peer_model": "switch",
                        "rel_id": 11,
                    }
                ]
            if int(dev_id) == 456:
                return [
                    {
                        "dev_id": 456,
                        "dev_name": "sw-mid",
                        "dev_model": "switch",
                        "local_if": "Eth1/2",
                        "peer_if": "Te0/1",
                        "peer_id": 999,
                        "peer_name": "sw-leaf",
                        "peer_model": "switch",
                        "rel_id": 22,
                    }
                ]
            return []

        ag = MagicMock()
        ag.query_network_topo.side_effect = _topo
        mock_gc.return_value.__enter__.return_value = ag
        mock_map.return_value = {456: {"_id": 456}, 999: {"_id": 999}}
        # 仅 999 有权限；中间的 456 无权限
        mock_perm.side_effect = lambda inst, pm, user=None: bool(inst) and inst.get("_id") == 999

        result = InstanceManage.network_topology(123, "switch", depth=2, permission_map={"1": {"inst_names": []}}, user=None)
        # 456 被剪枝、999 不可达：只剩中心，无连线，无孤点
        assert {n["id"] for n in result["nodes"]} == {"123"}
        assert result["links"] == []
        # 不应继续查询无权限设备 456 的下一跳
        queried = {int(c.args[0]) for c in ag.query_network_topo.call_args_list}
        assert queried == {123}

    @patch("apps.cmdb.services.instance.GraphClient")
    def test_node_limit_truncates(self, mock_gc):
        # 中心一跳就有 3 个对端，node_limit=2（含中心）→ 截断
        ag = MagicMock()
        ag.query_network_topo.return_value = [
            {
                "dev_id": 123,
                "dev_name": "sw-core",
                "dev_model": "switch",
                "local_if": f"Gi0/{i}",
                "peer_if": "Eth1/1",
                "peer_id": 400 + i,
                "peer_name": f"sw-{i}",
                "peer_model": "switch",
                "rel_id": i,
            }
            for i in range(1, 4)
        ]
        mock_gc.return_value.__enter__.return_value = ag

        result = InstanceManage.network_topology(123, "switch", depth=1, permission_map=None, user=None, node_limit=2)
        assert result["truncated"] is True
        # 中心 + 1 个对端达到上限 2，后续对端被截断
        assert len(result["nodes"]) == 2
        # 悬空边（指向被截断节点）已剔除，两端都在节点集中
        ids = {n["id"] for n in result["nodes"]}
        assert all(item["source_device"] in ids and item["target_device"] in ids for item in result["links"])


UUID_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
UUID_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
UUID_C = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
UUID_MISSING = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"


def _closed_set_entities():
    return [
        {"_id": 123, "inst_uuid": UUID_A, "model_id": "switch", "inst_name": "sw-a"},
        {"_id": 456, "inst_uuid": UUID_B, "model_id": "switch", "inst_name": "sw-b"},
        {"_id": 789, "inst_uuid": UUID_C, "model_id": "router", "inst_name": "r-c"},
    ]


@pytest.mark.unit
class TestNetworkTopologyAmongUuids:
    @patch("apps.cmdb.services.topology_theme.is_network_device_model", return_value=True)
    @patch("apps.cmdb.services.instance.InstanceManage.query_entity_by_uuids")
    @patch("apps.cmdb.services.instance.GraphClient")
    def test_keeps_only_edges_inside_selected_set_and_retains_islands(self, mock_gc, mock_entities, _mock_network):
        mock_entities.return_value = _closed_set_entities()
        ag = MagicMock()

        def _topo(inst_id, belong_asst_id):
            if inst_id == 123:
                return [
                    {
                        "dev_id": 123,
                        "dev_name": "sw-a",
                        "dev_model": "switch",
                        "local_if": "Gi0/1",
                        "peer_if": "Eth1/1",
                        "peer_id": 456,
                        "peer_name": "sw-b",
                        "peer_model": "switch",
                        "rel_id": 11,
                    },
                    {
                        "dev_id": 123,
                        "dev_name": "sw-a",
                        "dev_model": "switch",
                        "local_if": "Gi0/2",
                        "peer_if": "Eth9/9",
                        "peer_id": 999,
                        "peer_name": "outside",
                        "peer_model": "switch",
                        "rel_id": 99,
                    },
                ]
            return []

        ag.query_network_topo.side_effect = _topo
        mock_gc.return_value.__enter__.return_value = ag

        result = InstanceManage.network_topology_among_uuids([UUID_A, UUID_B, UUID_C])

        assert {n["id"] for n in result["nodes"]} == {UUID_A, UUID_B, UUID_C}
        assert [(n["id"], n["model_id"]) for n in result["nodes"]] == [
            (UUID_A, "switch"),
            (UUID_B, "switch"),
            (UUID_C, "router"),
        ]
        assert len(result["links"]) == 1
        link = result["links"][0]
        assert {link["source_device"], link["target_device"]} == {UUID_A, UUID_B}
        assert result.get("truncated") is False
        assert not result.get("center")

    @patch("apps.cmdb.services.topology_theme.is_network_device_model", return_value=True)
    @patch("apps.cmdb.services.instance.InstanceManage.query_entity_by_uuids")
    def test_missing_uuid_fails_closed(self, mock_entities, _mock_network):
        mock_entities.return_value = _closed_set_entities()[:2]
        with pytest.raises(Exception, match="重新配置"):
            InstanceManage.network_topology_among_uuids([UUID_A, UUID_B, UUID_MISSING])

    @patch("apps.cmdb.services.topology_theme.is_network_device_model", return_value=False)
    @patch("apps.cmdb.services.instance.InstanceManage.query_entity_by_uuids")
    def test_non_network_model_fails_closed(self, mock_entities, _mock_network):
        mock_entities.return_value = _closed_set_entities()[:1]
        with pytest.raises(Exception, match="重新配置"):
            InstanceManage.network_topology_among_uuids([UUID_A])

    @patch("apps.cmdb.services.topology_theme.is_network_device_model", return_value=True)
    @patch("apps.cmdb.services.instance.InstanceManage._has_topology_view_permission")
    @patch("apps.cmdb.services.instance.InstanceManage.query_entity_by_uuids")
    def test_denied_device_fails_closed(self, mock_entities, mock_perm, _mock_network):
        mock_entities.return_value = _closed_set_entities()[:2]
        mock_perm.side_effect = lambda inst, pm, user=None: inst and inst.get("_id") == 123
        with pytest.raises(Exception, match="重新配置"):
            InstanceManage.network_topology_among_uuids(
                [UUID_A, UUID_B],
                permission_maps={"switch": {"1": {}}},
            )
