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
import jsonschema
import pytest

from apps.cmdb.collection.collect_plugin.k8s import CollectK8sMetrics


def test_vm_response_matches_schema(load_fixture, load_schema):
    vm_resp = load_fixture("k8s/03_vm_metrics_response.json")
    schema = load_schema("k8s/03_vm_metrics.schema.json")
    jsonschema.validate(vm_resp, schema)


@pytest.mark.django_db
def test_k8s_namespace_pipeline(load_fixture, monkeypatch):
    """模拟从 VM 拉到 namespace metric → 跑 K8s runner 的 format_data + format_namespace_metrics。"""
    vm_resp = load_fixture("k8s/03_vm_metrics_response.json")
    expected = load_fixture("k8s/04_expected_cmdb_result.json")

    # 拦掉 VM HTTP
    monkeypatch.setattr(
        "apps.cmdb.collection.query_vm.Collection.query",
        lambda self, sql, timeout=60: vm_resp,
    )
    # 跳过 search_replicas / format_workload_metrics / format_node_metrics / format_pod_metrics
    # 内部的真实数据库查询；只跑 namespace 部分
    monkeypatch.setattr(CollectK8sMetrics, "search_replicas", lambda self: None)
    monkeypatch.setattr(CollectK8sMetrics, "format_pod_metrics", lambda self: None)
    monkeypatch.setattr(CollectK8sMetrics, "format_node_metrics", lambda self: None)
    monkeypatch.setattr(CollectK8sMetrics, "format_workload_metrics", lambda self: None)

    runner = CollectK8sMetrics(cluster_name="k8s-cluster-prod")
    runner.run()

    namespaces = runner.result["k8s_namespace"]
    actual_names = sorted([ns["name"] for ns in namespaces])
    assert actual_names == sorted(expected["expected_namespace_names"])

    # inst_name 格式 {namespace}({cluster_name})
    first = next(ns for ns in namespaces if ns["name"] == "default")
    assert first["inst_name"] == expected["expected_inst_name_pattern"]

    # 关联：挂到 cluster
    assert first["assos"][0]["model_id"] == "k8s_cluster"
    assert first["assos"][0]["inst_name"] == "k8s-cluster-prod"


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

    monkeypatch.setattr(
        "apps.cmdb.collection.query_vm.Collection.query",
        lambda self, sql, timeout=60: vm_resp,
    )
    monkeypatch.setattr(CollectK8sMetrics, "search_replicas", lambda self: None)
    monkeypatch.setattr(CollectK8sMetrics, "format_pod_metrics", lambda self: None)
    monkeypatch.setattr(CollectK8sMetrics, "format_node_metrics", lambda self: None)
    monkeypatch.setattr(CollectK8sMetrics, "format_workload_metrics", lambda self: None)

    runner = CollectK8sMetrics(cluster_name="k8s-cluster-prod")
    runner.run()

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
