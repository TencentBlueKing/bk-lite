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
