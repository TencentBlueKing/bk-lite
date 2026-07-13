import pytest
from rest_framework.exceptions import ValidationError

from apps.cmdb.services.k8s_resource_overview import K8sResourceOverviewService


@pytest.fixture
def k8s_graph(monkeypatch):
    instances = {
        1: {"_id": 1, "model_id": "k8s_cluster", "inst_name": "prod", "last_reported_at": "2026-07-10T10:00:00Z"},
        10: {"_id": 10, "model_id": "k8s_namespace", "inst_name": "default(prod)", "name": "default"},
        11: {"_id": 11, "model_id": "k8s_namespace", "inst_name": "ops(prod)", "name": "ops"},
        20: {"_id": 20, "model_id": "k8s_workload", "inst_name": "api(prod/default)", "name": "api", "workload_type": "deployment", "replicas": 3},
        21: {"_id": 21, "model_id": "k8s_workload", "inst_name": "backup(prod/ops)", "name": "backup", "workload_type": "job"},
        22: {"_id": 22, "model_id": "k8s_workload", "inst_name": "api-rs(prod/default)", "name": "api-rs", "workload_type": "replicaset"},
        30: {"_id": 30, "model_id": "k8s_pod", "inst_name": "api-1(prod/default)", "name": "api-1", "namespace": "default", "node": "node-a", "ip_addr": "10.0.0.30"},
        31: {"_id": 31, "model_id": "k8s_pod", "inst_name": "api-2(prod/default)", "name": "api-2", "namespace": "default", "node": "", "ip_addr": "10.0.0.31"},
        32: {"_id": 32, "model_id": "k8s_pod", "inst_name": "orphan(prod/default)", "name": "orphan", "namespace": "default", "node": "node-b"},
        40: {"_id": 40, "model_id": "k8s_node", "inst_name": "node-a(prod)", "name": "node-a", "role": "worker", "cpu": 8},
        41: {"_id": 41, "model_id": "k8s_node", "inst_name": "node-b(prod)", "name": "node-b", "role": "worker", "cpu": 16},
        99: {"_id": 99, "model_id": "k8s_cluster", "inst_name": "other"},
        199: {"_id": 199, "model_id": "k8s_workload", "inst_name": "other-wl", "name": "other-wl", "workload_type": "deployment"},
    }

    def group(src_model, dst_model, items, model_asst_id):
        return {
            "src_model_id": src_model,
            "dst_model_id": dst_model,
            "model_asst_id": model_asst_id,
            "asst_id": "belong",
            "inst_list": [instances[item] for item in items],
        }

    associations = {
        ("k8s_cluster", 1): [
            group("k8s_namespace", "k8s_cluster", [10, 11], "namespace_cluster"),
            group("k8s_node", "k8s_cluster", [40, 41], "node_cluster"),
        ],
        ("k8s_namespace", 10): [
            group("k8s_workload", "k8s_namespace", [20, 22], "workload_namespace"),
            group("k8s_pod", "k8s_namespace", [32], "pod_namespace"),
        ],
        ("k8s_namespace", 11): [group("k8s_workload", "k8s_namespace", [21], "workload_namespace")],
        ("k8s_workload", 20): [group("k8s_pod", "k8s_workload", [30, 31], "pod_workload")],
        ("k8s_workload", 21): [],
        ("k8s_workload", 22): [],
        ("k8s_pod", 30): [group("k8s_pod", "k8s_node", [40], "pod_node")],
        ("k8s_pod", 31): [],
        ("k8s_pod", 32): [group("k8s_pod", "k8s_node", [41], "pod_node")],
        ("k8s_cluster", 99): [],
        ("k8s_workload", 199): [],
    }

    monkeypatch.setattr(
        "apps.cmdb.services.k8s_resource_overview.InstanceManage.query_entity_by_id",
        lambda inst_id: instances.get(int(inst_id)),
    )
    monkeypatch.setattr(
        "apps.cmdb.services.k8s_resource_overview.InstanceManage.instance_association_instance_list",
        lambda model_id, inst_id: associations.get((model_id, int(inst_id)), []),
    )
    reverse_maps = {
        ("k8s_node", "k8s_pod"): {40: [30], 41: [32]},
        ("k8s_pod", "k8s_namespace"): {30: [10], 31: [10], 32: [10]},
        ("k8s_pod", "k8s_workload"): {30: [20], 31: [20], 32: []},
    }

    def association_map(model_id, inst_ids, related_model=None):
        special = reverse_maps.get((model_id, related_model))
        if special is not None:
            return {int(inst_id): special.get(int(inst_id), []) for inst_id in inst_ids}
        return {
            int(inst_id): sorted(
                {
                    int(item["_id"])
                    for group in associations.get((model_id, int(inst_id)), [])
                    for item in group.get("inst_list", [])
                    if item.get("model_id") == related_model
                    or (
                        item.get("model_id") is None
                        and related_model in {group.get("src_model_id"), group.get("dst_model_id")}
                    )
                }
            )
            for inst_id in inst_ids
        }

    monkeypatch.setattr(
        "apps.cmdb.services.k8s_resource_overview.InstanceManage.instance_association_map", association_map
    )

    def test_name(row):
        return str(row.get("name") or row.get("inst_name") or "")

    def test_workload_type(row):
        value = row.get("workload_type")
        if isinstance(value, list):
            value = value[0] if value else ""
        return str(value or "").casefold()

    def query_page(inst_ids, page=1, page_size=50, order="inst_name", filters=None):
        rows = [instances[int(inst_id)] for inst_id in inst_ids if int(inst_id) in instances]
        for query_filter in filters or []:
            if query_filter["type"] == "str*":
                rows = [row for row in rows if query_filter["value"].casefold() in test_name(row).casefold()]
            elif query_filter["type"] == "list_any[]":
                rows = [row for row in rows if test_workload_type(row) in query_filter["value"]]
            elif query_filter["type"] == "list_none[]":
                rows = [row for row in rows if test_workload_type(row) not in query_filter["value"]]
        reverse = str(order).startswith("-")
        order_key = str(order).removeprefix("-")
        rows.sort(key=lambda item: str(item.get(order_key) or item.get("name") or ""), reverse=reverse)
        count = len(rows)
        start = (int(page) - 1) * int(page_size)
        return rows[start: start + int(page_size)], count

    monkeypatch.setattr(
        "apps.cmdb.services.k8s_resource_overview.InstanceManage.query_entity_page_by_ids",
        query_page,
    )
    monkeypatch.setattr(
        "apps.cmdb.services.k8s_resource_overview.InstanceManage._has_topology_view_permission",
        lambda instance, permission_map, user=None: (
            instance is not None
            and (
                not permission_map
                or int(instance["_id"]) in set(permission_map.get("visible_ids", []))
            )
        ),
    )
    return instances


@pytest.mark.unit
def test_overview_returns_default_layers_without_pod_nodes(k8s_graph):
    result = K8sResourceOverviewService.get_overview(1)

    assert result["summary"] == {
        "namespace_count": 2,
        "workload_count": 2,
        "other_workload_count": 1,
        "pod_count": 3,
        "node_count": 2,
    }
    assert {node["layer"] for node in result["topology"]["nodes"]} == {
        "cluster",
        "namespace",
        "workload",
        "node",
    }
    assert all(node["model_id"] != "k8s_pod" for node in result["topology"]["nodes"])


@pytest.mark.unit
def test_workload_is_resolved_from_namespace_association_metadata_when_entity_omits_model_id(k8s_graph):
    """Graph 关联实体不保证回填 model_id，关联组的 src/dst 模型才是可靠来源。"""
    k8s_graph[20].pop("model_id")

    result = K8sResourceOverviewService.list_resources(1, "deployment")

    assert [item["name"] for item in result["items"]] == ["api"]


@pytest.mark.unit
def test_workload_type_list_value_is_classified_as_business_workload(k8s_graph):
    """CMDB 枚举字段在真实图数据中可能返回单元素列表。"""
    k8s_graph[20]["workload_type"] = ["deployment"]

    deployment = K8sResourceOverviewService.list_resources(1, "deployment")
    other = K8sResourceOverviewService.list_resources(1, "other_workload")

    assert [item["name"] for item in deployment["items"]] == ["api"]
    assert "api" not in [item["name"] for item in other["items"]]


@pytest.mark.unit
def test_visibility_uses_each_model_permission_and_prunes_hidden_parents(k8s_graph):
    permission_maps = {
        "k8s_namespace": {"visible_ids": [10]},
        "k8s_workload": {"visible_ids": [20, 21, 22]},
        "k8s_pod": {"visible_ids": [30, 31, 32]},
        "k8s_node": {"visible_ids": [40]},
    }

    result = K8sResourceOverviewService.get_overview(1, permission_maps=permission_maps)

    assert result["summary"] == {
        "namespace_count": 1,
        "workload_count": 1,
        "other_workload_count": 1,
        "pod_count": 3,
        "node_count": 1,
    }
    assert "backup" not in {node["name"] for node in result["topology"]["nodes"]}
    assert "node-b" not in {node["name"] for node in result["topology"]["nodes"]}


@pytest.mark.unit
def test_workload_pods_use_real_edges_and_distinguish_node_states(k8s_graph):
    result = K8sResourceOverviewService.get_workload_pods(1, 20, page=1, page_size=50)

    assert result["count"] == 2
    assert {node["name"] for node in result["nodes"]} == {"api-1", "api-2", "未调度"}
    assert any(edge["source"] == "20" and edge["target"] == "30" for edge in result["edges"])
    assert any(edge["source"] == "30" and edge["target"] == "40" for edge in result["edges"])
    assert any(edge["source"] == "31" and edge["target"] == "virtual:unscheduled" for edge in result["edges"])


@pytest.mark.unit
def test_workload_pods_paginate_and_reject_cross_cluster_workload(k8s_graph):
    page_one = K8sResourceOverviewService.get_workload_pods(1, 20, page=1, page_size=1)
    page_two = K8sResourceOverviewService.get_workload_pods(1, 20, page=2, page_size=1)

    assert page_one["count"] == 2
    assert [node["id"] for node in page_one["nodes"] if node["model_id"] == "k8s_pod"] == ["30"]
    assert [node["id"] for node in page_two["nodes"] if node["model_id"] == "k8s_pod"] == ["31"]
    with pytest.raises(ValidationError, match="不属于当前集群"):
        K8sResourceOverviewService.get_workload_pods(1, 199, page=1, page_size=50)


@pytest.mark.unit
def test_unowned_pods_report_hidden_node_without_leaking_name(k8s_graph):
    permission_maps = {"k8s_node": {"visible_ids": [40]}}

    result = K8sResourceOverviewService.get_unowned_pods(1, permission_maps=permission_maps)

    assert result["count"] == 1
    assert "node-b" not in str(result)
    assert any(node["id"] == "virtual:node-forbidden" for node in result["nodes"])


@pytest.mark.unit
def test_resource_list_supports_kind_search_and_relation_filters(k8s_graph):
    deployments = K8sResourceOverviewService.list_resources(1, "deployment", page=1, page_size=20)
    pods_on_node = K8sResourceOverviewService.list_resources(1, "pod", page=1, page_size=20, node_id=40)
    workloads_in_namespace = K8sResourceOverviewService.list_resources(
        1, "other_workload", page=1, page_size=20, namespace_id=10, search="rs"
    )

    assert [item["name"] for item in deployments["items"]] == ["api"]
    assert [item["name"] for item in pods_on_node["items"]] == ["api-1"]
    assert [item["name"] for item in workloads_in_namespace["items"]] == ["api-rs"]


@pytest.mark.unit
def test_collection_facts_are_raw_and_allow_missing_values(k8s_graph):
    result = K8sResourceOverviewService.get_overview(1)

    assert result["collection_facts"]["last_reported_at"] == "2026-07-10T10:00:00Z"
    assert result["collection_facts"]["last_success_at"] is None
    assert result["collection_facts"]["last_error"] is None
    assert "state" not in result["collection_facts"]


@pytest.mark.unit
def test_base_layers_use_stable_limits_and_parent_complete_workloads(monkeypatch):
    cluster = {"_id": 1, "model_id": "k8s_cluster", "inst_name": "prod"}
    namespaces = [
        {"_id": 100 + idx, "model_id": "k8s_namespace", "inst_name": f"ns-{idx:02d}", "name": f"ns-{idx:02d}"}
        for idx in range(25)
    ]
    nodes = [
        {"_id": 300 + idx, "model_id": "k8s_node", "inst_name": f"node-{idx:02d}", "name": f"node-{idx:02d}"}
        for idx in range(55)
    ]
    workloads = {
        ns["_id"]: [
            {
                "_id": 1000 + offset * 3 + child,
                "model_id": "k8s_workload",
                "inst_name": f"wl-{offset:02d}-{child}",
                "name": f"wl-{offset:02d}-{child}",
                "workload_type": "deployment",
            }
            for child in range(3)
        ]
        for offset, ns in enumerate(namespaces)
    }

    def association(model_id, inst_id):
        if (model_id, int(inst_id)) == ("k8s_cluster", 1):
            return [
                {"src_model_id": "k8s_namespace", "dst_model_id": "k8s_cluster", "model_asst_id": "namespace_cluster", "inst_list": namespaces},
                {"src_model_id": "k8s_node", "dst_model_id": "k8s_cluster", "model_asst_id": "node_cluster", "inst_list": nodes},
            ]
        if model_id == "k8s_namespace":
            return [{"src_model_id": "k8s_workload", "dst_model_id": "k8s_namespace", "model_asst_id": "workload_namespace", "inst_list": workloads.get(int(inst_id), [])}]
        return []

    monkeypatch.setattr(
        "apps.cmdb.services.k8s_resource_overview.InstanceManage.query_entity_by_id",
        lambda inst_id: cluster if int(inst_id) == 1 else None,
    )
    monkeypatch.setattr(
        "apps.cmdb.services.k8s_resource_overview.InstanceManage.instance_association_instance_list",
        association,
    )
    all_instances = {int(item["_id"]): item for item in [cluster, *namespaces, *nodes]}
    all_instances.update({int(item["_id"]): item for rows in workloads.values() for item in rows})

    def association_map(model_id, inst_ids, related_model=None):
        result = {}
        for inst_id in inst_ids:
            result[int(inst_id)] = sorted(
                {
                    int(item["_id"])
                    for group in association(model_id, int(inst_id))
                    for item in group.get("inst_list", [])
                    if item.get("model_id") == related_model
                }
            )
        return result

    def query_page(inst_ids, page=1, page_size=50, order="inst_name"):
        rows = [all_instances[int(inst_id)] for inst_id in inst_ids if int(inst_id) in all_instances]
        rows.sort(key=lambda item: str(item.get(order) or item.get("name") or ""))
        start = (int(page) - 1) * int(page_size)
        return rows[start: start + int(page_size)], len(rows)

    monkeypatch.setattr(
        "apps.cmdb.services.k8s_resource_overview.InstanceManage.instance_association_map", association_map
    )
    monkeypatch.setattr(
        "apps.cmdb.services.k8s_resource_overview.InstanceManage.query_entity_page_by_ids", query_page
    )

    result = K8sResourceOverviewService.get_overview(1)

    assert result["layers"]["namespace"] == {"shown": 20, "count": 25, "page_size": 20}
    assert result["layers"]["workload"] == {"shown": 50, "count": 60, "page_size": 50}
    assert result["layers"]["node"] == {"shown": 50, "count": 55, "page_size": 50}
    visible_ids = {node["id"] for node in result["topology"]["nodes"]}
    parent_by_workload = {edge["target"]: edge["source"] for edge in result["topology"]["edges"] if edge["kind"] == "namespace-workload"}
    assert parent_by_workload
    assert all(parent_id in visible_ids for parent_id in parent_by_workload.values())


@pytest.mark.unit
def test_overview_uses_batched_relations_and_never_loads_pod_entities(monkeypatch):
    """默认概览的查询预算必须与 Namespace/Workload 数量无关，且不能读取 Pod 实体。"""
    instances = {
        1: {"_id": 1, "model_id": "k8s_cluster", "inst_name": "prod"},
        10: {"_id": 10, "model_id": "k8s_namespace", "name": "default"},
        11: {"_id": 11, "model_id": "k8s_namespace", "name": "ops"},
        20: {"_id": 20, "model_id": "k8s_workload", "name": "api", "workload_type": "deployment"},
        21: {"_id": 21, "model_id": "k8s_workload", "name": "backup", "workload_type": "job"},
        40: {"_id": 40, "model_id": "k8s_node", "name": "node-a"},
    }
    relation_calls = []
    entity_queries = []

    def association_map(model_id, inst_ids, related_model=None):
        relation_calls.append((model_id, tuple(inst_ids), related_model))
        maps = {
            ("k8s_cluster", "k8s_namespace"): {1: [10, 11]},
            ("k8s_cluster", "k8s_node"): {1: [40]},
            ("k8s_namespace", "k8s_workload"): {10: [20], 11: [21]},
            ("k8s_workload", "k8s_pod"): {20: [30, 31], 21: [32]},
            ("k8s_namespace", "k8s_pod"): {10: [], 11: []},
        }
        return maps[(model_id, related_model)]

    def query_page(ids, page=1, page_size=50, order="inst_name"):
        entity_queries.append(tuple(ids))
        rows = [instances[item_id] for item_id in ids if item_id in instances]
        rows.sort(key=lambda item: str(item.get(order) or item.get("name") or ""))
        start = (page - 1) * page_size
        return rows[start: start + page_size], len(rows)

    monkeypatch.setattr(
        "apps.cmdb.services.k8s_resource_overview.InstanceManage.query_entity_by_id",
        lambda inst_id: instances.get(int(inst_id)),
    )
    monkeypatch.setattr(
        "apps.cmdb.services.k8s_resource_overview.InstanceManage.instance_association_map",
        association_map,
    )
    monkeypatch.setattr(
        "apps.cmdb.services.k8s_resource_overview.InstanceManage.query_entity_page_by_ids",
        query_page,
        raising=False,
    )
    monkeypatch.setattr(
        "apps.cmdb.services.k8s_resource_overview.InstanceManage.instance_association_instance_list",
        lambda *args, **kwargs: pytest.fail("概览不得逐实例查询关联"),
    )

    result = K8sResourceOverviewService.get_overview(1)

    assert result["summary"]["pod_count"] == 3
    assert len(relation_calls) == 5
    assert all(not ({30, 31, 32} & set(ids)) for ids in entity_queries)


@pytest.mark.unit
def test_workload_pod_page_batches_node_relations_for_current_page(monkeypatch):
    instances = {
        1: {"_id": 1, "model_id": "k8s_cluster", "name": "prod"},
        20: {"_id": 20, "model_id": "k8s_workload", "name": "api"},
        30: {"_id": 30, "model_id": "k8s_pod", "name": "api-1", "node": "node-a"},
        31: {"_id": 31, "model_id": "k8s_pod", "name": "api-2", "node": "node-b"},
        41: {"_id": 41, "model_id": "k8s_node", "name": "node-b"},
    }
    page_queries = []
    relation_calls = []

    def association_map(model_id, inst_ids, related_model=None):
        relation_calls.append((model_id, tuple(inst_ids), related_model))
        maps = {
            ("k8s_cluster", "k8s_namespace"): {1: [10]},
            ("k8s_namespace", "k8s_workload"): {10: [20]},
            ("k8s_workload", "k8s_pod"): {20: [30, 31]},
            ("k8s_pod", "k8s_node"): {31: [41]},
        }
        return maps[(model_id, related_model)]

    def query_page(ids, page=1, page_size=50, order="inst_name"):
        page_queries.append(tuple(ids))
        rows = [instances[item_id] for item_id in ids if item_id in instances]
        start = (page - 1) * page_size
        return rows[start: start + page_size], len(ids)

    monkeypatch.setattr(
        "apps.cmdb.services.k8s_resource_overview.InstanceManage.query_entity_by_id",
        lambda inst_id: instances.get(int(inst_id)),
    )
    monkeypatch.setattr(
        "apps.cmdb.services.k8s_resource_overview.InstanceManage.instance_association_map", association_map
    )
    monkeypatch.setattr(
        "apps.cmdb.services.k8s_resource_overview.InstanceManage.query_entity_page_by_ids", query_page
    )
    monkeypatch.setattr(
        "apps.cmdb.services.k8s_resource_overview.InstanceManage.instance_association_instance_list",
        lambda *args, **kwargs: pytest.fail("Pod 页不得逐实例查询关联"),
    )

    result = K8sResourceOverviewService.get_workload_pods(1, 20, page=2, page_size=1)

    assert result["count"] == 2
    assert any(edge["source"] == "31" and edge["target"] == "41" for edge in result["edges"])
    assert relation_calls[-1] == ("k8s_pod", (31,), "k8s_node")
    assert page_queries[0] == (30, 31)
