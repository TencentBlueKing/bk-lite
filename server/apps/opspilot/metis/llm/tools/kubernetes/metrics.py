"""Kubernetes Metrics Server top 工具。"""

import json

from kubernetes import client
from kubernetes.client import ApiException
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.metis.llm.tools.kubernetes.utils import prepare_context

_METRICS_GROUP = "metrics.k8s.io"
_METRICS_VERSION = "v1beta1"


def _metrics_error(exc, kind: str) -> str:
    status = getattr(exc, "status", None)
    if status == 404:
        return json.dumps(
            {
                "error": "Metrics Server 不可用或未安装（metrics.k8s.io 返回 404）",
                "metrics_available": False,
                "source": "metrics.k8s.io",
            },
            ensure_ascii=False,
        )
    return json.dumps(
        {"error": f"获取{kind}指标失败: {exc}", "metrics_available": False, "source": "metrics.k8s.io"},
        ensure_ascii=False,
    )


def _pod_usage_item(item: dict) -> dict:
    meta = item.get("metadata") or {}
    containers = []
    cpu = None
    memory = None
    for container in item.get("containers") or []:
        usage = container.get("usage") or {}
        containers.append({"name": container.get("name"), "cpu": usage.get("cpu"), "memory": usage.get("memory")})
        if cpu is None:
            cpu = usage.get("cpu")
            memory = usage.get("memory")
    return {
        "name": meta.get("name"),
        "namespace": meta.get("namespace"),
        "cpu": cpu,
        "memory": memory,
        "containers": containers,
    }


@tool()
def get_kubernetes_pods_top(namespace=None, pod_name=None, config: RunnableConfig = None):
    """
    查询 Pod CPU/内存用量（Metrics Server，类似 kubectl top pods）

    用于区分探针过紧、CPU throttle、内存压力。Metrics Server 未安装时返回 metrics_available=false。
    """
    prepare_context(config)
    try:
        api = client.CustomObjectsApi()
        if namespace:
            data = api.list_namespaced_custom_object(_METRICS_GROUP, _METRICS_VERSION, namespace, "pods")
        else:
            data = api.list_cluster_custom_object(_METRICS_GROUP, _METRICS_VERSION, "pods")
        items = data.get("items") or []
        pods = [_pod_usage_item(item) for item in items]
        if pod_name:
            pods = [pod for pod in pods if pod.get("name") == pod_name]
        logger.info("get_kubernetes_pods_top completed namespace=%s count=%s", namespace, len(pods))
        return json.dumps({"source": "metrics.k8s.io", "metrics_available": True, "pods": pods}, ensure_ascii=False)
    except ApiException as exc:
        return _metrics_error(exc, "Pod")
    except Exception as exc:
        return json.dumps({"error": f"获取Pod指标失败: {exc}", "metrics_available": False}, ensure_ascii=False)


@tool()
def get_kubernetes_nodes_top(node_name=None, config: RunnableConfig = None):
    """
    查询节点 CPU/内存用量（Metrics Server，类似 kubectl top nodes）
    """
    prepare_context(config)
    try:
        api = client.CustomObjectsApi()
        data = api.list_cluster_custom_object(_METRICS_GROUP, _METRICS_VERSION, "nodes")
        nodes = []
        for item in data.get("items") or []:
            meta = item.get("metadata") or {}
            usage = item.get("usage") or {}
            nodes.append({"name": meta.get("name"), "cpu": usage.get("cpu"), "memory": usage.get("memory")})
        if node_name:
            nodes = [node for node in nodes if node.get("name") == node_name]
        logger.info("get_kubernetes_nodes_top completed count=%s", len(nodes))
        return json.dumps({"source": "metrics.k8s.io", "metrics_available": True, "nodes": nodes}, ensure_ascii=False)
    except ApiException as exc:
        return _metrics_error(exc, "Node")
    except Exception as exc:
        return json.dumps({"error": f"获取Node指标失败: {exc}", "metrics_available": False}, ensure_ascii=False)
