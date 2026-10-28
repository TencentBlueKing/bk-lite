from unittest.mock import patch

import pytest

from apps.cmdb.nats import nats
from apps.cmdb.services.asset_overview_query import (
    AssetOverviewQueryError,
    assemble_resource_rows,
    build_association_option_items,
    build_classification_count_items,
    normalize_cloud_region_ids,
    query_cloud_region_resource_counts,
    resolve_supplement_tag,
    select_model_endpoint_associations,
)

MODELS = [
    {"model_id": "host", "model_name": "主机"},
    {"model_id": "mysql", "model_name": "MySQL"},
    {"model_id": "redis", "model_name": "Redis"},
]


def test_cloud_region_ids_keep_order_and_reject_blanks():
    assert normalize_cloud_region_ids(["2", 2, 7]) == [2, 7]
    with pytest.raises(AssetOverviewQueryError, match="云区域不能为空"):
        normalize_cloud_region_ids([])
    with pytest.raises(AssetOverviewQueryError, match="云区域 ID 无效"):
        normalize_cloud_region_ids([True])


def test_supplement_tag_ignores_incomplete_input():
    assert resolve_supplement_tag("", None) is None
    assert resolve_supplement_tag("数据中心", " ") is None
    assert resolve_supplement_tag("", "测试") is None
    assert resolve_supplement_tag("数据中心", "金融云") == "数据中心:金融云"


def test_rows_dedupe_and_keep_zero_models():
    rows = assemble_resource_rows(
        host_uuids=["h1", "h1", "h2"],
        ordered_peer_models=["mysql", "redis"],
        peers_by_model={"mysql": {"db1", "db-shared"}, "redis": set()},
        tag_instances=[
            ("db-shared", "mysql"),
            ("db-free", "mysql"),
            ("room-1", "room"),
            ("other-host", "host"),
            ("linked", "oracle"),
        ],
        host_associated_uuids={"linked"},
        model_names={"host": "主机", "mysql": "MySQL", "redis": "Redis", "room": "机房", "oracle": "Oracle"},
    )

    assert [(row["model_id"], row["value"]) for row in rows] == [
        ("mysql", 3),
        ("redis", 0),
        ("room", 1),
        ("host", 2),
    ]
    assert rows[0]["label"] == "MySQL"


def test_classification_counts_follow_selection_order_and_keep_zero():
    items = build_classification_count_items(
        ["database", "host_mgmt"],
        [
            {"classification_id": "host_mgmt", "classification_name": "主机"},
            {"classification_id": "database", "classification_name": "数据库"},
        ],
        [
            {"model_id": "mysql", "classification_id": "database"},
            {"model_id": "redis", "classification_id": "database"},
            {"model_id": "host", "classification_id": "host_mgmt"},
        ],
        {"mysql": 2, "redis": 0, "host": 5},
    )
    assert [(item["classification_id"], item["value"]) for item in items] == [("database", 2), ("host_mgmt", 5)]


def test_missing_classification_fails():
    with pytest.raises(AssetOverviewQueryError, match="不可见"):
        build_classification_count_items(["missing"], [], [], {})


def test_association_options_keep_only_one_host_end():
    associations = [
        {"model_asst_id": "mysql_run_host", "src_model_id": "mysql", "dst_model_id": "host"},
        {"model_asst_id": "host_belong_vm", "src_model_id": "host", "dst_model_id": "vm"},
        {"model_asst_id": "fusion_belong", "src_model_id": "fusioncompute_host", "dst_model_id": "fusioncompute"},
        {"model_asst_id": "host_link_host", "src_model_id": "host", "dst_model_id": "host"},
    ]
    selected = select_model_endpoint_associations(associations, "host")
    assert [item["model_asst_id"] for item in selected] == ["mysql_run_host", "host_belong_vm"]
    with pytest.raises(AssetOverviewQueryError, match="模型不能为空"):
        select_model_endpoint_associations(associations, " ")


def test_association_option_label_uses_both_models():
    items = build_association_option_items(
        [
            {
                "model_asst_id": "mysql_run_host",
                "asst_name": "运行",
                "src_model_id": "mysql",
                "dst_model_id": "host",
                "src_model_name": "MySQL",
                "dst_model_name": "主机",
            }
        ]
    )
    assert items == [
        {
            "model_asst_id": "mysql_run_host",
            "label": "MySQL —运行— 主机",
            "src_model_id": "mysql",
            "dst_model_id": "host",
            "asst_name": "运行",
        }
    ]


class _Graph:
    def __init__(self, entities_by_model, tagged=None, host_edges=None):
        self.entities_by_model = entities_by_model
        self.tagged = tagged or []
        self.host_edges = host_edges or []
        self.entity_params = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def query_entity(self, label, params, **kwargs):
        del label, kwargs
        self.entity_params.append(params)
        if any(item.get("field") == "tag" for item in params):
            return self.tagged, len(self.tagged)
        model_id = next(item["value"] for item in params if item["field"] == "model_id")
        rows = self.entities_by_model.get(model_id, [])
        uuid_filter = next((item["value"] for item in params if item["field"] == "inst_uuid"), None)
        if uuid_filter is not None:
            rows = [row for row in rows if row["inst_uuid"] in set(uuid_filter)]
        return rows, len(rows)

    def query_edge(self, label, params, **kwargs):
        del label, params, kwargs
        return self.host_edges


@pytest.mark.unit
def test_resource_counts_follow_association_then_tag_then_host():
    graph = _Graph(
        entities_by_model={
            "host": [{"inst_uuid": "h1", "model_id": "host"}],
            "mysql": [{"inst_uuid": "db1", "model_id": "mysql"}],
        },
        tagged=[
            {"inst_uuid": "db-free", "model_id": "mysql"},
            {"inst_uuid": "linked", "model_id": "redis"},
            {"inst_uuid": "room-1", "model_id": "room"},
        ],
        host_edges=[{"src_inst_uuid": "linked", "src_model_id": "redis", "dst_inst_uuid": "h9", "dst_model_id": "host"}],
    )

    def edges(model_asst_id, host_uuids, graph=None):
        del host_uuids, graph
        if model_asst_id == "mysql_run_host":
            return [{"src_inst_uuid": "db1", "src_model_id": "mysql", "dst_inst_uuid": "h1", "dst_model_id": "host"}]
        return []

    with patch("apps.cmdb.services.asset_overview_query.GraphClient", return_value=graph), patch(
        "apps.cmdb.services.asset_overview_query.ModelManage.model_association_info_search",
        side_effect=lambda model_asst_id: {
            "mysql_run_host": {"src_model_id": "mysql", "dst_model_id": "host"},
            "redis_run_host": {"src_model_id": "redis", "dst_model_id": "host"},
        }[model_asst_id],
    ), patch("apps.cmdb.services.asset_overview_query.query_association_edges", side_effect=edges):
        rows = query_cloud_region_resource_counts(
            [7],
            ["mysql_run_host", "redis_run_host"],
            "数据中心",
            "金融云",
            instance_permission_map={1: {"inst_names": []}},
            visible_models=MODELS + [{"model_id": "room", "model_name": "机房"}],
        )

    assert [(row["model_id"], row["value"]) for row in rows] == [
        ("mysql", 2),
        ("redis", 0),
        ("room", 1),
        ("host", 1),
    ]
    assert graph.entity_params[0][1] == {"field": "cloud", "type": "int[]", "value": [7]}


@pytest.mark.unit
def test_empty_hosts_keep_zero_rows_and_do_not_scan_associations():
    graph = _Graph(
        entities_by_model={"host": []},
        tagged=[{"inst_uuid": "room-1", "model_id": "room"}],
    )
    with patch("apps.cmdb.services.asset_overview_query.GraphClient", return_value=graph), patch(
        "apps.cmdb.services.asset_overview_query.ModelManage.model_association_info_search",
        return_value={"src_model_id": "mysql", "dst_model_id": "host"},
    ), patch("apps.cmdb.services.asset_overview_query.query_association_edges") as edges:
        rows = query_cloud_region_resource_counts(
            [7],
            ["mysql_run_host"],
            "数据中心",
            "金融云",
            instance_permission_map={1: {"inst_names": []}},
            visible_models=MODELS + [{"model_id": "room", "model_name": "机房"}],
        )
    edges.assert_not_called()
    assert [(row["model_id"], row["value"]) for row in rows] == [("mysql", 0), ("room", 1), ("host", 0)]
    assert graph.entity_params[0] == [
        {"field": "model_id", "type": "str=", "value": "host"},
        {"field": "cloud", "type": "int[]", "value": [7]},
    ]
    assert any(item.get("field") == "tag" for item in graph.entity_params[1])
    assert len(graph.entity_params) == 2


@pytest.mark.unit
def test_association_without_host_fails():
    with patch(
        "apps.cmdb.services.asset_overview_query.ModelManage.model_association_info_search",
        return_value={"src_model_id": "mysql", "dst_model_id": "redis"},
    ):
        with pytest.raises(AssetOverviewQueryError, match="必须连接主机"):
            query_cloud_region_resource_counts(
                [7],
                ["mysql_run_redis"],
                instance_permission_map={1: {"inst_names": []}},
                visible_models=MODELS,
            )


@pytest.mark.unit
def test_one_database_on_two_hosts_counts_once():
    graph = _Graph(
        entities_by_model={
            "host": [{"inst_uuid": "h1", "model_id": "host"}, {"inst_uuid": "h2", "model_id": "host"}],
            "mysql": [{"inst_uuid": "db1", "model_id": "mysql"}],
        }
    )

    def edges(model_asst_id, host_uuids, graph=None):
        del model_asst_id, host_uuids, graph
        return [
            {"src_inst_uuid": "db1", "src_model_id": "mysql", "dst_inst_uuid": "h1", "dst_model_id": "host"},
            {"src_inst_uuid": "db1", "src_model_id": "mysql", "dst_inst_uuid": "h2", "dst_model_id": "host"},
        ]

    with patch("apps.cmdb.services.asset_overview_query.GraphClient", return_value=graph), patch(
        "apps.cmdb.services.asset_overview_query.ModelManage.model_association_info_search",
        return_value={"src_model_id": "mysql", "dst_model_id": "host"},
    ), patch("apps.cmdb.services.asset_overview_query.query_association_edges", side_effect=edges):
        rows = query_cloud_region_resource_counts(
            [7],
            ["mysql_run_host"],
            instance_permission_map={1: {"inst_names": []}},
            visible_models=MODELS,
        )
    assert [(row["model_id"], row["value"]) for row in rows] == [("mysql", 1), ("host", 2)]


USER_INFO = {"team": 1, "user": "alice", "language": "zh-CN"}


@pytest.mark.unit
@patch.object(nats, "list_model_association_options", return_value=[{"model_asst_id": "mysql_run_host"}])
def test_association_options_pass_fixed_model(listed):
    result = nats.get_model_association_options(model_id="host", user_info=USER_INFO)
    listed.assert_called_once_with("zh-Hans", "host")
    assert result == {"result": True, "data": [{"model_asst_id": "mysql_run_host"}], "message": ""}


@pytest.mark.unit
@patch.object(nats, "NodeMgmt", create=True)
def test_cloud_region_options_use_region_id(node_mgmt):
    node_mgmt.return_value.cloud_region_list.return_value = [{"id": 7, "name": "金融云"}, {"id": None, "name": "空"}]
    with patch("apps.rpc.node_mgmt.NodeMgmt", node_mgmt):
        assert nats.get_cloud_region_options(user_info=USER_INFO) == {
            "result": True,
            "data": [{"id": 7, "name": "金融云"}],
            "message": "",
        }


@pytest.mark.unit
@patch.object(nats.InstanceManage, "model_inst_count", return_value={"mysql": 2, "host": 0})
@patch.object(
    nats.ClassificationManage,
    "search_model_classification",
    return_value=[
        {"classification_id": "database", "classification_name": "数据库"},
        {"classification_id": "host_mgmt", "classification_name": "主机"},
    ],
)
@patch.object(
    nats.ModelManage,
    "search_model",
    return_value=[
        {"model_id": "mysql", "classification_id": "database"},
        {"model_id": "host", "classification_id": "host_mgmt"},
    ],
)
@patch.object(nats, "_build_nats_permission_map", return_value={1: {"inst_names": []}})
@patch.object(nats, "_build_nats_model_permission_map", return_value={1: {"inst_names": []}})
def test_classification_counts_keep_requested_order(model_perm, inst_perm, models, classifications, counts):
    del model_perm, inst_perm, models, classifications, counts
    result = nats.get_classification_instance_counts(classification_ids=["host_mgmt", "database"], user_info=USER_INFO)
    assert result["result"] is True
    assert [(item["classification_id"], item["value"]) for item in result["data"]] == [("host_mgmt", 0), ("database", 2)]
    narrowed = nats.get_classification_instance_counts(
        classification_ids=["database"],
        all_visible="true",
        user_info=USER_INFO,
    )
    assert [item["classification_id"] for item in narrowed["data"]] == ["database"]
    expanded = nats.get_classification_instance_counts(classification_ids=[], all_visible="true", user_info=USER_INFO)
    assert [item["classification_id"] for item in expanded["data"]] == ["database", "host_mgmt"]


@pytest.mark.unit
def test_classification_counts_reject_empty_selection_without_all_visible():
    with pytest.raises(nats.AssetOverviewQueryError, match="分类不能为空"):
        nats.get_classification_instance_counts(classification_ids=[], user_info=USER_INFO)


@pytest.mark.unit
@patch.object(nats, "_build_nats_model_permission_map", return_value=None)
def test_resource_counts_without_permission_are_empty(model_perm):
    del model_perm
    assert nats.get_cloud_region_resource_counts(cloud_region_ids=[1], model_asst_ids=["mysql_run_host"], user_info=USER_INFO) == {
        "result": True,
        "data": [],
        "message": "",
    }


@pytest.mark.unit
def test_classification_instance_counts_is_registered_and_helper_is_not():
    from nats_client.registry import default_registry

    names = {item["name"] for item in default_registry.registry.values()}
    assert "get_classification_instance_counts" in names
    assert "_classification_all_visible" not in names
