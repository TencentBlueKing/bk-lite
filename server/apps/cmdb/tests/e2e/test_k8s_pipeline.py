"""K8s 采集端到端流水线测试 —— k8s 大类代表。

K8s 与其他大类的本质差异：
  - runner CollectK8sMetrics 不继承 CollectBase，__init__ 签名独特：(cluster_name, **kwargs)
  - run() 一次性查全部 metric（namespace/workload/node/pod 4 分组）
  - 业务逻辑硬编码（不走 plugin field_mapping），通过 namespace/workload/node/pod 4 个独立 format_* 方法分别处理
  - 因此 K8s 走不了通用 generic 驱动；本测试用最小化路径直接驱动 namespace 子分组转换

校验目标：
  - VM 响应 schema 契约
  - namespace metric → CMDB k8s_namespace 实例（inst_name 格式 = {ns}({cluster})）
  - 关联关系：每个 namespace 应挂到 cluster
  - Task 2.2 新增 4 分组（namespace/workload/pod/node）真实化覆盖
"""
import copy
from collections import Counter

import jsonschema
import pytest

from apps.cmdb.collection.collect_plugin.k8s import CollectK8sMetrics
from apps.cmdb.collection.constants import REPLICAS_METRICS

SNAPSHOT_TIMESTAMP = "prometheus_cmdb_k8s_snapshot_timestamp"
SNAPSHOT_COUNT = "prometheus_cmdb_k8s_snapshot_count"
CLUSTER_NAME = "k8s-cluster-prod"
ROUND_TS = 1700000000
MARKER_TS = 1700000100


def _snapshot_count_rows(resource_rows):
    """计数行覆盖 get_metrics 与副本指标，条数与同批资源行一致。"""
    names = set(CollectK8sMetrics.get_metrics()) | set(REPLICAS_METRICS)
    actual = Counter(row["metric"]["__name__"] for row in resource_rows)
    return [
        {
            "metric": {
                "__name__": SNAPSHOT_COUNT,
                "resource_metric": name.removeprefix("prometheus_"),
            },
            "value": [MARKER_TS, str(actual[name])],
        }
        for name in sorted(names)
    ]


def _patch_vm_query(monkeypatch, vm_resp, marker_timestamp=None):
    """标记查询返回空结果或一条标记；其余查询返回 k8s/03 资源样本。"""
    query_calls = []
    resource_rows = copy.deepcopy(vm_resp["data"]["result"])

    def query_metrics(self, sql, timeout=60, min_timestamp=None, max_timestamp=None):
        query_calls.append((sql, min_timestamp, max_timestamp))
        if SNAPSHOT_TIMESTAMP in sql:
            if marker_timestamp is None:
                return {"status": "success", "data": {"resultType": "vector", "result": []}}
            return {
                "status": "success",
                "data": {
                    "resultType": "vector",
                    "result": [
                        {
                            "metric": {
                                "__name__": SNAPSHOT_TIMESTAMP,
                                "instance_id": CLUSTER_NAME,
                                "snapshot_contract_version": "1",
                            },
                            "value": [marker_timestamp, str(marker_timestamp)],
                        }
                    ],
                },
            }
        rows = copy.deepcopy(resource_rows)
        if marker_timestamp is not None and SNAPSHOT_COUNT in sql:
            rows.extend(_snapshot_count_rows(resource_rows))
        return {"status": "success", "data": {"resultType": "vector", "result": rows}}

    monkeypatch.setattr("apps.cmdb.collection.query_vm.Collection.query", query_metrics)
    return query_calls


def _skip_non_namespace_formatters(monkeypatch):
    monkeypatch.setattr(CollectK8sMetrics, "search_replicas", lambda self: None)
    monkeypatch.setattr(CollectK8sMetrics, "format_pod_metrics", lambda self: None)
    monkeypatch.setattr(CollectK8sMetrics, "format_node_metrics", lambda self: None)
    monkeypatch.setattr(CollectK8sMetrics, "format_workload_metrics", lambda self: None)


def _assert_namespace_expectations(runner, expected):
    namespaces = runner.result["k8s_namespace"]
    actual_names = sorted(ns["name"] for ns in namespaces)
    assert actual_names == sorted(expected["expected_namespace_names"])
    first = next(ns for ns in namespaces if ns["name"] == "default")
    assert first["inst_name"] == expected["expected_inst_name_pattern"]
    assert first["assos"][0]["model_id"] == "k8s_cluster"
    assert first["assos"][0]["inst_name"] == CLUSTER_NAME
    assert all(row["metric"]["__name__"] not in {SNAPSHOT_TIMESTAMP, SNAPSHOT_COUNT} for row in runner.raw_data)


def test_vm_response_matches_schema(load_fixture, load_schema):
    vm_resp = load_fixture("k8s/03_vm_metrics_response.json")
    schema = load_schema("k8s/03_vm_metrics.schema.json")
    jsonschema.validate(vm_resp, schema)


@pytest.mark.django_db
def test_k8s_namespace_pipeline(load_fixture, monkeypatch):
    """模拟从 VM 拉到 namespace metric → 跑 K8s runner 的 format_data + format_namespace_metrics。"""
    vm_resp = load_fixture("k8s/03_vm_metrics_response.json")
    expected = load_fixture("k8s/04_expected_cmdb_result.json")

    query_calls = _patch_vm_query(monkeypatch, vm_resp)
    # 跳过 search_replicas / format_workload_metrics / format_node_metrics / format_pod_metrics
    # 内部的真实数据库查询；只跑 namespace 部分
    _skip_non_namespace_formatters(monkeypatch)

    runner = CollectK8sMetrics(cluster_name=CLUSTER_NAME, round_ts=ROUND_TS)
    runner.run()
    assert len(query_calls) == 2
    assert SNAPSHOT_TIMESTAMP in query_calls[0][0]
    assert query_calls[0][1] != ROUND_TS
    assert 'instance_id="k8s-cluster-prod"' in query_calls[1][0]
    assert query_calls[1][1] == ROUND_TS
    assert query_calls[1][2] is None
    assert runner.snapshot_complete is False
    _assert_namespace_expectations(runner, expected)


def test_drift_detection(load_schema):
    bad = {
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": [{
                "metric": {"__name__": "non_k8s_metric", "instance_id": "x"},  # 不符合 prometheus_kube_ prefix
                "value": [1, "1"],
            }],
        },
    }
    schema = load_schema("k8s/03_vm_metrics.schema.json")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


# ============================================================================
# Task 2.2: k8s_namespace 4 分组(workspace / pod / node)真实化覆盖
# ============================================================================


@pytest.mark.django_db
def test_k8s_4_group_coverage(load_fixture, monkeypatch):
    """K8s 4 分组 metric 全部跑通:namespace + workload + pod + node。

    minimal path:只跑 format_data + format_namespace + 跳过 search_replicas / 其他 3 个 format_*
    (它们内部会查 FalkorDB,不属于本测试范围)。
    """
    vm_resp = load_fixture("k8s/03_vm_metrics_response.json")
    expected = load_fixture("k8s/04_expected_cmdb_result.json")

    query_calls = _patch_vm_query(monkeypatch, vm_resp)
    _skip_non_namespace_formatters(monkeypatch)

    runner = CollectK8sMetrics(cluster_name=CLUSTER_NAME, round_ts=ROUND_TS)
    runner.run()
    assert len(query_calls) == 2
    assert SNAPSHOT_TIMESTAMP in query_calls[0][0]
    assert query_calls[0][1] != ROUND_TS
    assert 'instance_id="k8s-cluster-prod"' in query_calls[1][0]
    assert query_calls[1][1] == ROUND_TS
    assert query_calls[1][2] is None
    assert runner.snapshot_complete is False

    # namespace 全部采集
    namespaces = runner.result["k8s_namespace"]
    actual_names = sorted([ns["name"] for ns in namespaces])
    assert actual_names == sorted(expected["expected_namespace_names"])

    # raw_data 4 分组都有数据(用于下游 format_* 处理)
    raw_metrics = {item["metric"]["__name__"] for item in runner.raw_data}
    # 至少包含以下 metric 类型
    assert any(m.startswith("prometheus_kube_namespace_labels") for m in raw_metrics)
    assert any(m.startswith("prometheus_kube_deployment_created") for m in raw_metrics)
    assert any(m.startswith("prometheus_kube_statefulset_created") for m in raw_metrics)
    assert any(m.startswith("prometheus_kube_daemonset_created") for m in raw_metrics)
    assert any(m.startswith("prometheus_kube_job_info") for m in raw_metrics)
    assert any(m.startswith("prometheus_kube_cronjob_info") for m in raw_metrics)
    assert any(m.startswith("prometheus_kube_pod_info") for m in raw_metrics)
    assert any(m.startswith("prometheus_kube_node_info") for m in raw_metrics)


@pytest.mark.django_db
def test_k8s_marked_snapshot_uses_resource_rows(load_fixture, monkeypatch):
    """有快照标记时，上下界都用标记时间，namespace 仍来自资源行。"""
    vm_resp = load_fixture("k8s/03_vm_metrics_response.json")
    expected = load_fixture("k8s/04_expected_cmdb_result.json")

    query_calls = _patch_vm_query(monkeypatch, vm_resp, marker_timestamp=MARKER_TS)
    _skip_non_namespace_formatters(monkeypatch)

    runner = CollectK8sMetrics(cluster_name=CLUSTER_NAME, round_ts=ROUND_TS)
    runner.run()
    assert len(query_calls) == 2
    assert SNAPSHOT_TIMESTAMP in query_calls[0][0]
    assert query_calls[1][1] == MARKER_TS
    assert query_calls[1][2] == MARKER_TS
    assert SNAPSHOT_COUNT in query_calls[1][0]
    assert runner.snapshot_complete is True
    _assert_namespace_expectations(runner, expected)


def test_k8s_a_b_alignment(load_fixture, load_schema):
    """k8s_namespace A/B 端对齐走 minimal path 占位校验。

    真实采集路径是 CollectK8sMetrics.run() 一次性拉 4 分组 metric,不经过 stargazer 标准化 step1。
    因此 A 端 metric name / B 端 instance 字段对齐走 K8s 特定 schema(非通用 04 schema),
    A/B 端 alignment test 在 test_stargazer_prometheus_alignment.py / test_cmdb_vm_format_alignment.py
    里均走 pytest.skip。本测试只验证:
      - 01 fixture 存在(placeholder)
      - 04 schema 反映 k8s_namespace 实例结构
    """
    raw = load_fixture("k8s_namespace/01_stargazer_raw.json")
    assert raw["_placeholder_reason"] is not None

    schema = load_schema("k8s/04_cmdb_instance.schema.json")
    # 验证 schema 反映 k8s_namespace 实例结构
    assert "inst_name" in schema["properties"]
    assert "name" in schema["properties"]
    assert "model_id" in schema["properties"]
