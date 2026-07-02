"""Kubernetes 集群检查/连接 @tool 单元测试 (kubernetes/cluster)。

纯函数工具(explain_kubernetes_resource / kubernetes_troubleshooting_guide /
_get_api_version_for_resource)直接断言静态知识库分派;API 驱动工具
(verify_kubernetes_connection / list_kubernetes_api_resources /
describe_kubernetes_resource)mock prepare_context 与 client.*Api,断言版本/权限
探测、API 资源聚合、describe 分派与 404/不支持类型/异常包装。
get_kubernetes_contexts 走 multi-instance 与本地 kubeconfig 两条分支。不连真实集群。
"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pydantic.root_model  # noqa
import pytest
from kubernetes.client import ApiException

from apps.opspilot.metis.llm.tools.kubernetes import cluster as c


# ---------------- pure tools ----------------
class TestExplainResource:
    def test_known_resource(self):
        out = json.loads(c.explain_kubernetes_resource.invoke({"resource_type": "Pod"}))
        assert out["resource_type"] == "pod"
        assert out["api_version"] == "v1"
        assert "spec.containers" in out["key_fields"]

    def test_deployment_api_version(self):
        out = json.loads(c.explain_kubernetes_resource.invoke(
            {"resource_type": "deployment"}))
        assert out["api_version"] == "apps/v1"

    def test_unknown_resource(self):
        out = json.loads(c.explain_kubernetes_resource.invoke(
            {"resource_type": "widget"}))
        assert "error" in out
        assert "pod" in out["supported_types"]


class TestApiVersionHelper:
    def test_mapping(self):
        assert c._get_api_version_for_resource("statefulset") == "apps/v1"
        assert c._get_api_version_for_resource("node") == "v1"
        assert c._get_api_version_for_resource("unknownthing") == "未知"


class TestTroubleshootingGuide:
    def test_known_keyword(self):
        out = json.loads(c.kubernetes_troubleshooting_guide.invoke(
            {"keyword": "POD", "namespace": "prod"}))
        assert out["title"] == "Pod故障排查指导"
        assert out["namespace_context"] == "prod"
        assert len(out["steps"]) == 5

    def test_network_keyword(self):
        out = json.loads(c.kubernetes_troubleshooting_guide.invoke(
            {"keyword": "network"}))
        assert "网络" in out["title"]

    def test_unknown_keyword(self):
        out = json.loads(c.kubernetes_troubleshooting_guide.invoke(
            {"keyword": "quantum"}))
        assert "error" in out
        assert "storage" in out["available_keywords"]


# ---------------- API driven ----------------
@pytest.fixture
def apis():
    core, apps = MagicMock(), MagicMock()
    with patch.object(c, "prepare_context", return_value=None), \
         patch.object(c.client, "CoreV1Api", return_value=core), \
         patch.object(c.client, "AppsV1Api", return_value=apps):
        yield core, apps


class TestVerifyConnection:
    def test_success_via_call_api(self, apis):
        core, _ = apis
        core.api_client.call_api.return_value = (
            {"gitVersion": "v1.28.0", "platform": "linux/amd64"},)
        core.list_namespace.return_value = SimpleNamespace(items=[])
        out = json.loads(c.verify_kubernetes_connection.invoke({"config": {}}))
        assert out["connection_status"] == "成功"
        assert out["kubernetes_version"] == "v1.28.0"
        assert out["permissions"] == "有基本读取权限"

    def test_fallback_to_version_api(self, apis):
        core, _ = apis
        core.api_client.call_api.side_effect = Exception("no /version")
        with patch.object(c.client, "VersionApi") as VApi:
            VApi.return_value.get_code.return_value = SimpleNamespace(
                git_version="v1.27.3", platform="linux/arm64")
            core.list_namespace.return_value = SimpleNamespace(items=[])
            out = json.loads(c.verify_kubernetes_connection.invoke({"config": {}}))
        assert out["kubernetes_version"] == "v1.27.3"
        assert out["platform"] == "linux/arm64"

    def test_permission_restricted(self, apis):
        core, _ = apis
        core.api_client.call_api.return_value = ({"gitVersion": "v1.28.0"},)
        err = ApiException(status=403)
        err.reason = "Forbidden"
        core.list_namespace.side_effect = err
        out = json.loads(c.verify_kubernetes_connection.invoke({"config": {}}))
        assert "权限受限" in out["permissions"]
        assert out["namespace_access"] == "受限"

    def test_connection_failure(self, apis):
        core, _ = apis
        with patch.object(c, "prepare_context", side_effect=Exception("conn refused")):
            out = json.loads(c.verify_kubernetes_connection.invoke({"config": {}}))
        assert out["connection_status"] == "失败"
        assert "conn refused" in out["error"]


class TestListApiResources:
    def test_aggregates_core_resources(self, apis):
        core, _ = apis
        res = SimpleNamespace(name="pods", short_names=["po"], kind="Pod",
                              namespaced=True, verbs=["get", "list"])
        sub = SimpleNamespace(name="pods/log", short_names=None, kind="Pod",
                              namespaced=True, verbs=None)
        core.get_api_resources.return_value = SimpleNamespace(resources=[res, sub])
        with patch.object(c.client, "ApiClient") as AC, \
             patch.object(c.client, "ApisApi") as ApisApi, \
             patch.object(c.client, "CoreV1Api", return_value=core):
            ApisApi.return_value.get_api_versions.return_value = SimpleNamespace(
                groups=[])
            out = json.loads(c.list_kubernetes_api_resources.invoke({"config": {}}))
        names = [r["name"] for r in out["api_resources"]]
        assert "pods" in names  # core resource included
        assert "pods/log" not in names  # subresource excluded
        assert out["filtered_by"] == "所有API组"

    def test_exception_wrapped(self, apis):
        with patch.object(c, "prepare_context", side_effect=Exception("boom")):
            out = json.loads(c.list_kubernetes_api_resources.invoke({"config": {}}))
        assert "error" in out
        assert out["total_count"] == 0


class TestDescribeResource:
    def test_pod_requires_namespace(self, apis):
        out = json.loads(c.describe_kubernetes_resource.invoke(
            {"resource_type": "pod", "resource_name": "p", "config": {}}))
        assert "需要指定namespace" in out["error"]

    def test_node_describe(self, apis):
        core, _ = apis
        node = SimpleNamespace()
        core.read_node.return_value = node
        with patch.object(c.client, "ApiClient") as AC:
            AC.return_value.sanitize_for_serialization.return_value = {
                "metadata": {"name": "n1", "labels": {"a": "b"}},
                "spec": {"unschedulable": False},
                "status": {"phase": "Ready"},
            }
            out = json.loads(c.describe_kubernetes_resource.invoke(
                {"resource_type": "node", "resource_name": "n1", "config": {}}))
        assert out["name"] == "n1"
        assert out["resource_type"] == "node"
        assert out["labels"] == {"a": "b"}

    def test_unsupported_type(self, apis):
        out = json.loads(c.describe_kubernetes_resource.invoke(
            {"resource_type": "widget", "resource_name": "x", "config": {}}))
        assert "暂不支持" in out["error"]
        assert "pod" in out["supported_types"]

    def test_not_found_404(self, apis):
        core, _ = apis
        core.read_node.side_effect = ApiException(status=404)
        out = json.loads(c.describe_kubernetes_resource.invoke(
            {"resource_type": "node", "resource_name": "ghost", "config": {}}))
        assert out["status_code"] == 404

    def test_other_api_error(self, apis):
        core, _ = apis
        err = ApiException(status=500)
        core.read_namespace.side_effect = err
        out = json.loads(c.describe_kubernetes_resource.invoke(
            {"resource_type": "namespace", "resource_name": "x", "config": {}}))
        assert out["status_code"] == 500


class TestGetContexts:
    def test_multi_instance(self):
        kubeconfig = (
            "current-context: ctx1\n"
            "contexts:\n"
            "- name: ctx1\n"
            "  context:\n"
            "    cluster: c1\n"
            "    user: u1\n"
            "    namespace: ns1\n"
        )
        instances = [
            {"name": "prod", "id": "1", "kubeconfig_data": kubeconfig},
            {"name": "dev", "id": "2", "kubeconfig_data": kubeconfig},
        ]
        with patch("apps.opspilot.metis.llm.tools.kubernetes.connection."
                   "get_kubernetes_instances_from_configurable",
                   return_value=instances):
            out = json.loads(c.get_kubernetes_contexts.func(
                config={"configurable": {"kubernetes_instances": [1, 2]}}))
        assert len(out["clusters"]) == 2
        assert out["clusters"][0]["contexts"][0]["cluster"] == "c1"
        assert "_instruction" in out  # >1 cluster triggers instruction

    def test_local_kubeconfig_fallback(self):
        contexts = [{"name": "ctx1", "context": {"cluster": "c", "user": "u"}}]
        active = {"name": "ctx1"}
        with patch("kubernetes.config.list_kube_config_contexts",
                   return_value=(contexts, active)):
            out = json.loads(c.get_kubernetes_contexts.invoke({"config": {}}))
        assert out["current_context"] == "ctx1"
        assert out["available_contexts"][0]["is_current"] is True

    def test_local_kubeconfig_error(self):
        with patch("kubernetes.config.list_kube_config_contexts",
                   side_effect=Exception("no config")):
            out = json.loads(c.get_kubernetes_contexts.invoke({"config": {}}))
        assert "获取集群信息失败" in out["error"]
