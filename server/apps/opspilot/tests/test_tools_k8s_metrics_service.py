"""Kubernetes Metrics Server top 工具单测。不连真实集群。"""

import json
from unittest.mock import MagicMock, patch

import pydantic.root_model  # noqa
import pytest
from kubernetes.client import ApiException

from apps.opspilot.metis.llm.tools.kubernetes import metrics as m


@pytest.fixture
def custom_api():
    api = MagicMock()
    with patch.object(m, "prepare_context", return_value=None), patch.object(m.client, "CustomObjectsApi", return_value=api):
        yield api


class TestPodsTop:
    def test_lists_pod_usage(self, custom_api):
        custom_api.list_cluster_custom_object.return_value = {
            "items": [
                {
                    "metadata": {"name": "nacos-0", "namespace": "nacos"},
                    "containers": [{"name": "nacos", "usage": {"cpu": "50m", "memory": "256Mi"}}],
                }
            ]
        }
        out = json.loads(m.get_kubernetes_pods_top.invoke({"config": {}}))
        assert out["source"] == "metrics.k8s.io"
        assert out["pods"][0]["name"] == "nacos-0"
        assert out["pods"][0]["cpu"] == "50m"
        assert out["pods"][0]["memory"] == "256Mi"

    def test_metrics_server_missing(self, custom_api):
        custom_api.list_cluster_custom_object.side_effect = ApiException(status=404, reason="Not Found")
        out = json.loads(m.get_kubernetes_pods_top.invoke({"config": {}}))
        assert "error" in out
        assert out.get("metrics_available") is False


class TestNodesTop:
    def test_lists_node_usage(self, custom_api):
        custom_api.list_cluster_custom_object.return_value = {
            "items": [
                {
                    "metadata": {"name": "worker-1"},
                    "usage": {"cpu": "500m", "memory": "4Gi"},
                }
            ]
        }
        out = json.loads(m.get_kubernetes_nodes_top.invoke({"config": {}}))
        assert out["nodes"][0]["name"] == "worker-1"
        assert out["nodes"][0]["cpu"] == "500m"
