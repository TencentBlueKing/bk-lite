"""Kubernetes 告警驱动数据采集编排工具。"""

from __future__ import annotations

import copy
import json
import re
import threading
from datetime import datetime, timezone

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.opspilot.metis.llm.tools.kubernetes.cluster import describe_kubernetes_resource
from apps.opspilot.metis.llm.tools.kubernetes.node_diagnostics import diagnose_node_issues
from apps.opspilot.metis.llm.tools.kubernetes.optimization import compare_deployment_revisions
from apps.opspilot.metis.llm.tools.kubernetes.remediation import get_deployment_revision_history
from apps.opspilot.metis.llm.tools.kubernetes.resources import get_kubernetes_pod_logs, get_kubernetes_previous_pod_logs
from apps.opspilot.metis.llm.tools.kubernetes.tracing import get_resource_events_timeline, trace_service_chain


def _configurable(config: RunnableConfig = None):
    return config.get("configurable", {}) if config else {}


def _build_instance_config(config: RunnableConfig, instance: dict):
    configurable = copy.deepcopy(_configurable(config))
    configurable["instance_id"] = instance.get("id")
    configurable["instance_name"] = instance.get("name")
    configurable["kubeconfig_data"] = instance.get("kubeconfig_data", "")
    return {"configurable": configurable}


def _get_target_instances(config: RunnableConfig = None, instance_name=None, instance_id=None):
    from apps.opspilot.metis.llm.tools.kubernetes.connection import get_kubernetes_instances_from_configurable, resolve_kubernetes_instance

    configurable = _configurable(config)
    instances = get_kubernetes_instances_from_configurable(configurable)
    if not instances:
        return []
    if instance_id or instance_name:
        return [resolve_kubernetes_instance(instances, instance_name=instance_name, instance_id=instance_id)]
    return instances


def _collect_single_instance_context(target, scope, config: RunnableConfig = None):
    resource_type = (target.get("resource_type") or "").lower()

    if resource_type == "pod":
        payload = _collect_pod_context(target, scope)
    elif resource_type == "node":
        payload = _collect_node_context(target, scope)
    elif resource_type == "service":
        payload = _collect_service_context(target, scope)
    elif resource_type == "deployment":
        payload = _collect_deployment_context(target, scope)
    else:
        payload = {
            "resource_snapshot": None,
            "events_timeline": None,
            "pod_logs": None,
            "node_context": None,
            "service_topology": None,
            "change_context": None,
            "missing_data": ["unsupported_resource_type"],
        }
    return payload


def _json_or_raw(value):
    if isinstance(value, (dict, list)):
        return value
    if value is None:
        return None
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return value
    return value


def _lookup_payload_error(value) -> str | None:
    payload = _json_or_raw(value)
    if isinstance(payload, dict):
        err = payload.get("error")
        if err not in (None, "", [], {}):
            return str(err)
    if isinstance(payload, str) and payload.strip():
        from apps.opspilot.metis.llm.common.tool_failure import is_non_replanable_tool_failure

        if is_non_replanable_tool_failure(payload):
            return payload.strip()
    return None


def _cluster_config_error(config: RunnableConfig = None) -> str | None:
    """kubeconfig 无效时尽早返回，避免被包装成「缺 namespace / 缺标识」。"""
    configurable = _configurable(config)
    if not configurable.get("kubernetes_instances") and not configurable.get("kubeconfig_data"):
        return None
    from apps.opspilot.metis.llm.tools.kubernetes.utils import prepare_context

    try:
        prepare_context(config)
    except Exception as exc:
        return str(exc).strip() or type(exc).__name__
    return None


def _unresolved_connection_result(target: dict, error: str) -> str:
    payload = dict(target or {})
    payload["resolved"] = False
    payload["error"] = error
    payload["conclusive"] = True
    payload["lookup_exhausted"] = True
    if not payload.get("reason"):
        payload["reason"] = error
    return json.dumps(payload, ensure_ascii=False)


def _evidence_block(value=None, *, status=None, error=None):
    if status is None:
        if error:
            status = "failed"
        elif value is None:
            status = "skipped"
        else:
            status = "success"
    return {"status": status, "data": value, "error": error}


def _first_non_empty(*values):
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


def _extract_owner_workload(snapshot):
    if not isinstance(snapshot, dict):
        return None
    metadata = snapshot.get("metadata") or {}
    owner_refs = metadata.get("ownerReferences") or metadata.get("owner_references") or []
    if not owner_refs:
        return None
    owner = owner_refs[0] or {}
    return {
        "kind": owner.get("kind"),
        "name": owner.get("name"),
        "uid": owner.get("uid"),
    }


def _append_unique(items, value):
    if value and value not in items:
        items.append(value)


def _extract_config_references(snapshot):
    if not isinstance(snapshot, dict):
        return {"config_maps": [], "secrets": []}

    config_maps = []
    secrets = []
    spec = snapshot.get("spec") or {}

    for volume in spec.get("volumes") or []:
        _append_unique(config_maps, ((volume.get("configMap") or {}).get("name")))
        _append_unique(secrets, ((volume.get("secret") or {}).get("secretName")))

    containers = spec.get("containers") or []
    for container in containers:
        for env_from in container.get("envFrom") or []:
            _append_unique(config_maps, ((env_from.get("configMapRef") or {}).get("name")))
            _append_unique(secrets, ((env_from.get("secretRef") or {}).get("name")))

        for env in container.get("env") or []:
            value_from = env.get("valueFrom") or {}
            _append_unique(config_maps, ((value_from.get("configMapKeyRef") or {}).get("name")))
            _append_unique(secrets, ((value_from.get("secretKeyRef") or {}).get("name")))

    return {"config_maps": config_maps, "secrets": secrets}


_SERVICE_DNS_PATTERN = re.compile(r"([a-z0-9]([-a-z0-9]*[a-z0-9])?)\.([a-z0-9]([-a-z0-9]*[a-z0-9])?)", re.IGNORECASE)


def _extract_service_reference_from_logs(*log_values):
    for value in log_values:
        if not isinstance(value, str) or not value:
            continue
        lowered = value.lower()
        if not any(keyword in lowered for keyword in ["no such host", "lookup ", "connection refused", "timeout", "service unavailable"]):
            continue
        match = _SERVICE_DNS_PATTERN.search(value)
        if match:
            return {"service_name": match.group(1), "namespace": match.group(3)}
    return None


def _enrich_pod_snapshot(snapshot):
    if not isinstance(snapshot, dict):
        return snapshot

    enriched = copy.deepcopy(snapshot)
    owner_workload = _extract_owner_workload(enriched)
    if owner_workload:
        enriched["owner_workload"] = owner_workload

    config_refs = _extract_config_references(enriched)
    if config_refs["config_maps"] or config_refs["secrets"]:
        enriched["config_references"] = config_refs

    return enriched


_K8S_KIND_NAMES = frozenset(
    {
        "pod",
        "deployment",
        "statefulset",
        "daemonset",
        "replicaset",
        "job",
        "cronjob",
        "service",
        "node",
    }
)
K8S_TARGET_RESOLVE_TOOL_NAME = "resolve_k8s_target_from_alert"
_resolve_cache_local = threading.local()


def _extract_labels(alert):
    labels = alert.get("labels") or {}
    labels = dict(labels) if isinstance(labels, dict) else {}
    # 模型常把 pod_name/namespace/name/kind 放在告警顶层而不是 labels 里
    for key in (
        "pod",
        "pod_name",
        "name",
        "namespace",
        "cluster",
        "cluster_id",
        "resource_name",
        "resource_type",
        "kind",
        "container",
        "node",
        "deployment",
        "service",
        "service_name",
    ):
        value = alert.get(key)
        if value not in (None, "", [], {}) and not labels.get(key):
            labels[key] = value
    return labels


_PAREN_GROUP_RE = re.compile(r"[（(]([^）)]+)[）)]")
_POD_LIKE_NAME_RE = re.compile(r"\b([a-z0-9](?:[-a-z0-9]*[a-z0-9])?(?:-[a-f0-9]{5,10}){1,2})\b", re.IGNORECASE)
_NOTIFICATION_TITLE_RE = re.compile(r"告警[：:]\s*(.+?)(?:\n|$)")
_NOTIFICATION_CONTENT_RE = re.compile(r"内容[：:]\s*(.+?)(?:\n|$)")
_NOTIFICATION_TIME_RE = re.compile(r"告警时间[：:]*\s*(.+?)(?:\n|$)")
_K8S_ALERT_SOURCE_NAMES = frozenset({"kubernetes", "k8s"})


def _parse_k8s_paren_tuple(text: str) -> dict:
    """从 `Unhealthy（kubernetes，cluster，nacos-0）` 提取 cluster 与对象名。

    忽略正文里 ASCII 括号（如 Client.Timeout exceeded ...），只认来源为 kubernetes/k8s 的三段元组。
    """
    parsed = {}
    if not isinstance(text, str) or not text.strip():
        return parsed
    for match in _PAREN_GROUP_RE.finditer(text):
        parts = [part.strip() for part in re.split(r"[,，、/|]", match.group(1)) if part.strip()]
        if len(parts) < 3 or parts[0].lower() not in _K8S_ALERT_SOURCE_NAMES:
            continue
        parsed["cluster"] = parts[1]
        parsed["pod"] = parts[-1]
        parsed["resource_name"] = parts[-1]
        break
    return parsed


def _parse_notification_alert_text(text: str) -> dict:
    payload = {"source": "notification", "labels": {}, "annotations": {}}
    title_match = _NOTIFICATION_TITLE_RE.search(text)
    content_match = _NOTIFICATION_CONTENT_RE.search(text)
    time_match = _NOTIFICATION_TIME_RE.search(text)
    payload["title"] = title_match.group(1).strip() if title_match else text.strip().split("\n", 1)[0].strip()
    if content_match:
        payload["message"] = content_match.group(1).strip()
    else:
        payload["message"] = text.strip()
    if time_match:
        payload["firing_time"] = time_match.group(1).strip()
    payload["_raw_text"] = text
    return payload


def _coerce_alert_payload(alert_payload) -> dict:
    if isinstance(alert_payload, dict):
        return dict(alert_payload)
    if not isinstance(alert_payload, str):
        return {}
    text = alert_payload.strip()
    if not text:
        return {}
    if text[0] in "{[":
        try:
            loaded = json.loads(text)
        except Exception:
            loaded = None
        if isinstance(loaded, dict):
            return loaded
    return _parse_notification_alert_text(text)


def _merge_paren_labels(payload: dict) -> dict:
    labels = dict(payload.get("labels") or {}) if isinstance(payload.get("labels"), dict) else {}
    blob = "\n".join(str(payload.get(key) or "") for key in ("title", "name", "message", "summary", "detail", "content", "_raw_text"))
    for key, value in _parse_k8s_paren_tuple(blob).items():
        if value and not labels.get(key):
            labels[key] = value
    payload["labels"] = labels
    return payload


def _normalize_alert_event_payload(alert_payload) -> dict:
    payload = _merge_paren_labels(_coerce_alert_payload(alert_payload))
    labels = _extract_labels(payload)
    annotations = payload.get("annotations") if isinstance(payload.get("annotations"), dict) else {}
    return {
        "source": payload.get("source") or "unknown",
        "alert_id": payload.get("alert_id") or payload.get("id") or "",
        "title": payload.get("title") or payload.get("name") or "",
        "message": payload.get("message") or payload.get("summary") or payload.get("content") or payload.get("detail") or "",
        "severity": payload.get("severity") or payload.get("level") or "unknown",
        "status": payload.get("status") or "unknown",
        "firing_time": payload.get("firing_time") or payload.get("startsAt") or payload.get("starts_at"),
        "labels": labels,
        "annotations": annotations,
    }


def _guess_resource_name_from_text(*texts: str) -> str | None:
    """从告警标题/正文中猜测 Pod 名（含 ReplicaSet hash 后缀形态）。"""
    for text in texts:
        parsed = _parse_k8s_paren_tuple(text) if isinstance(text, str) else {}
        if parsed.get("pod"):
            return parsed["pod"]
    for text in texts:
        if not isinstance(text, str) or not text.strip():
            continue
        for match in _PAREN_GROUP_RE.finditer(text):
            parts = [part.strip() for part in re.split(r"[,，、/|]", match.group(1)) if part.strip()]
            # 典型：kubernetes，bk-lite-k3s，server-5b8fb979d7-csdcc
            if parts:
                candidate = parts[-1]
                if _POD_LIKE_NAME_RE.fullmatch(candidate) or "-" in candidate:
                    return candidate
        match = _POD_LIKE_NAME_RE.search(text)
        if match:
            return match.group(1)
    return None


def _flat_object_name(labels: dict) -> str | None:
    """顶层 name：仅在 kind 为 K8s 资源或名字像 Pod 时采用，避免把告警标题当对象名。"""
    candidate = labels.get("name")
    if candidate in (None, "", [], {}):
        return None
    text = str(candidate).strip()
    if not text:
        return None
    kind = str(labels.get("kind") or labels.get("resource_type") or "").lower()
    if kind in _K8S_KIND_NAMES:
        return text
    if _POD_LIKE_NAME_RE.fullmatch(text):
        return text
    return None


def _mark_target_conclusive(target: dict, *, lookup_exhausted: bool = False) -> dict:
    target["resolved"] = False
    target["conclusive"] = True
    if lookup_exhausted:
        target["lookup_exhausted"] = True
    return target


def _parse_k8s_target_payload(content) -> dict | None:
    payload = content
    if isinstance(content, str):
        text = content.strip()
        if not text or text[0] not in "{[":
            return None
        try:
            payload = json.loads(text)
        except Exception:
            return None
    if isinstance(payload, dict):
        return payload
    return None


def is_k8s_target_lookup_exhausted(content) -> bool:
    """反查已终态：对象不可见、标识不足或连接失败，同一参数再调不会变。"""
    payload = _parse_k8s_target_payload(content)
    if not payload:
        return False
    if payload.get("conclusive") is True or payload.get("lookup_exhausted") is True:
        return True
    if payload.get("resolved") is True:
        return False
    missing = payload.get("missing_data") or []
    return "namespace" in missing or "resource_type_or_name" in missing


def k8s_target_lookup_exhausted_from_messages(messages) -> bool:
    for message in reversed(messages or []):
        name = str(getattr(message, "name", "") or "")
        if name != K8S_TARGET_RESOLVE_TOOL_NAME:
            continue
        return is_k8s_target_lookup_exhausted(getattr(message, "content", None))
    return False


def _alert_resolve_fingerprint(alert: dict, config: RunnableConfig = None) -> str:
    keys = (
        "cluster",
        "kind",
        "name",
        "namespace",
        "pod",
        "pod_name",
        "resource_name",
        "resource_type",
        "labels",
        "title",
        "message",
        "detail",
    )
    slim = {key: (alert or {}).get(key) for key in keys}
    configurable = _configurable(config)
    slim["_conn"] = {
        "instance_id": configurable.get("instance_id"),
        "instance_name": configurable.get("instance_name"),
        "has_kubeconfig": bool(configurable.get("kubeconfig_data")),
        "has_instances": bool(configurable.get("kubernetes_instances")),
    }
    return json.dumps(slim, ensure_ascii=False, sort_keys=True, default=str)


def _resolve_alert_cache(config: RunnableConfig = None) -> dict:
    """同一线程内缓存反查结果。LangChain invoke 会复制 config，不能只写 configurable。"""
    configurable = _configurable(config)
    existing = configurable.get("_k8s_resolve_alert_cache")
    if isinstance(existing, dict):
        _resolve_cache_local.entries = existing
        return existing
    cache = getattr(_resolve_cache_local, "entries", None)
    if not isinstance(cache, dict):
        cache = {}
        _resolve_cache_local.entries = cache
    if configurable:
        configurable["_k8s_resolve_alert_cache"] = cache
    return cache


def _apply_namespace_lookup(target: dict, pods: list, events: list) -> dict:
    """在缺 namespace 时，用 Pod 列表 / Events 反查命名空间。"""
    resource_name = target.get("pod_name") or target.get("resource_name")
    if not resource_name or target.get("namespace"):
        return target

    namespaces = []
    for pod in pods or []:
        if not isinstance(pod, dict):
            continue
        if pod.get("name") == resource_name and pod.get("namespace"):
            namespaces.append(str(pod["namespace"]))

    if not namespaces:
        for event in events or []:
            if not isinstance(event, dict):
                continue
            obj = str(event.get("object") or "")
            if obj.endswith(f"/{resource_name}") or obj == resource_name:
                ns = event.get("namespace")
                if ns:
                    namespaces.append(str(ns))

    unique = list(dict.fromkeys(namespaces))
    if len(unique) == 1:
        target["namespace"] = unique[0]
        target["namespace_lookup"] = "pods_or_events"
        if "namespace" in (target.get("missing_data") or []):
            target["missing_data"] = [item for item in target["missing_data"] if item != "namespace"]
        if target.get("resource_type") and target.get("resource_name"):
            target["resolved"] = True
            target["reason"] = None
    elif len(unique) > 1:
        target["missing_data"] = list(dict.fromkeys((target.get("missing_data") or []) + ["namespace"]))
        target["namespace_candidates"] = unique
        target["resolved"] = False
        target["lookup_exhausted"] = True
        target["conclusive"] = True
        target["reason"] = f"Multiple namespaces matched resource {resource_name}: {', '.join(unique)}"
    else:
        target["missing_data"] = list(dict.fromkeys((target.get("missing_data") or []) + ["namespace"]))
        if not target.get("reason"):
            target["reason"] = f"Namespace not found for resource {resource_name} via pods/events lookup"
        target["resolved"] = False
        target["lookup_exhausted"] = True
        target["conclusive"] = True

    return target


def _build_k8s_target_from_alert(alert: dict) -> dict:
    labels = _extract_labels(alert)
    title = alert.get("title") or ""
    message = alert.get("message") or ""
    detail = alert.get("detail") or ""
    resource_type_label = str(labels.get("resource_type") or labels.get("kind") or "").lower()
    flat_name = _flat_object_name(labels)

    pod_name = _first_non_empty(
        labels.get("pod"),
        labels.get("pod_name"),
        labels.get("resource_name") if resource_type_label in ("", "pod") else None,
        flat_name if resource_type_label in ("", "pod") else None,
    )
    if not pod_name:
        pod_name = _guess_resource_name_from_text(title, message, detail)

    target = {
        "cluster": labels.get("cluster") or labels.get("cluster_id"),
        "namespace": labels.get("namespace"),
        "resource_type": None,
        "resource_name": None,
        "pod_name": pod_name,
        "container_name": labels.get("container"),
        "node_name": labels.get("node"),
        "deployment_name": labels.get("deployment"),
        "service_name": labels.get("service") or labels.get("service_name"),
        "resolved": False,
        "missing_data": [],
        "reason": None,
    }

    if target["pod_name"] or resource_type_label == "pod":
        target["resource_type"] = "pod"
        target["resource_name"] = target["pod_name"] or labels.get("resource_name") or (flat_name if resource_type_label == "pod" else None)
    elif target["node_name"] or resource_type_label == "node":
        target["resource_type"] = "node"
        target["resource_name"] = target["node_name"] or labels.get("resource_name") or (flat_name if resource_type_label == "node" else None)
    elif target["service_name"] or resource_type_label == "service":
        target["resource_type"] = "service"
        target["resource_name"] = target["service_name"] or labels.get("resource_name") or (flat_name if resource_type_label == "service" else None)
    elif target["deployment_name"] or resource_type_label == "deployment":
        target["resource_type"] = "deployment"
        target["resource_name"] = (
            target["deployment_name"] or labels.get("resource_name") or (flat_name if resource_type_label == "deployment" else None)
        )
    elif labels.get("resource_name") or flat_name:
        target["resource_type"] = resource_type_label or "pod"
        target["resource_name"] = labels.get("resource_name") or flat_name
        if target["resource_type"] == "pod":
            target["pod_name"] = target["resource_name"]

    if target["resource_type"] and target["resource_name"] and target["namespace"]:
        target["resolved"] = True
    elif not target["resource_type"] or not target["resource_name"]:
        target["reason"] = "Missing resource identifier needed to resolve Kubernetes target"
        target["missing_data"].append("resource_type_or_name")
        _mark_target_conclusive(target)
    elif not target["namespace"]:
        target["missing_data"].append("namespace")
        target["reason"] = "Missing namespace; will attempt pods/events reverse lookup"

    return target


@tool()
def normalize_alert_event(alert_payload, config: RunnableConfig = None):
    """标准化告警输入。接受结构化 dict 或 BK-Lite 通知纯文本。"""
    return json.dumps(_normalize_alert_event_payload(alert_payload), ensure_ascii=False)


@tool()
def resolve_k8s_target_from_alert(normalized_alert, config: RunnableConfig = None):
    """从标准化告警解析 K8s 目标；缺 namespace 时反查一次 Pod/Events。

    同一告警参数只应调用一次。返回 resolved=false 且 conclusive/lookup_exhausted 时
    表示对象当前不可见或标识不足，禁止用相同参数重试。
    """
    if isinstance(normalized_alert, str):
        try:
            parsed = json.loads(normalized_alert)
        except Exception:
            parsed = None
        if isinstance(parsed, dict):
            alert = parsed
        else:
            alert = _parse_notification_alert_text(normalized_alert)
    elif isinstance(normalized_alert, dict):
        alert = dict(normalized_alert)
    else:
        alert = {}
    if not isinstance(alert, dict):
        alert = {}
    alert = _merge_paren_labels(alert)

    cache = _resolve_alert_cache(config)
    fingerprint = _alert_resolve_fingerprint(alert, config)
    cached = cache.get(fingerprint)
    if isinstance(cached, str) and cached:
        return cached

    target = _build_k8s_target_from_alert(alert)

    connection_error = _cluster_config_error(config)
    if connection_error:
        result = _unresolved_connection_result(target, connection_error)
        cache[fingerprint] = result
        return result

    needs_lookup = bool(target.get("resource_name") or target.get("pod_name")) and not target.get("namespace")
    if needs_lookup:
        from apps.opspilot.metis.llm.tools.kubernetes.resources import list_kubernetes_events, list_kubernetes_pods

        try:
            pods_raw = list_kubernetes_pods.invoke({"namespace": None}, config=config)
            events_raw = list_kubernetes_events.invoke({"namespace": None}, config=config)
        except Exception as lookup_exc:
            result = _unresolved_connection_result(target, str(lookup_exc).strip() or type(lookup_exc).__name__)
            cache[fingerprint] = result
            return result
        lookup_error = _lookup_payload_error(pods_raw) or _lookup_payload_error(events_raw)
        if lookup_error:
            result = _unresolved_connection_result(target, lookup_error)
            cache[fingerprint] = result
            return result
        pods = _json_or_raw(pods_raw) or []
        events = _json_or_raw(events_raw) or []
        if not isinstance(pods, list):
            pods = []
        if not isinstance(events, list):
            events = []
        target = _apply_namespace_lookup(target, pods, events)

    if target.get("resource_type") and target.get("resource_name") and target.get("namespace"):
        target["resolved"] = True
        if not target.get("reason"):
            target["reason"] = None
    elif target.get("resource_type") and target.get("resource_name") and not target.get("namespace"):
        target["resolved"] = False
        target["missing_data"] = list(dict.fromkeys((target.get("missing_data") or []) + ["namespace"]))
        if not target.get("reason"):
            target["reason"] = "Missing namespace after pods/events reverse lookup"
        _mark_target_conclusive(target, lookup_exhausted=True)

    result = json.dumps(target, ensure_ascii=False)
    cache[fingerprint] = result
    return result


def _collect_pod_context(target, scope):
    namespace = target.get("namespace")
    pod_name = target.get("pod_name") or target.get("resource_name")
    container_name = target.get("container_name")
    node_name = target.get("node_name")
    minutes = int((scope or {}).get("time_window_minutes") or 60)
    lines = int((scope or {}).get("log_lines") or 100)

    resource_snapshot = _json_or_raw(describe_kubernetes_resource.invoke({"resource_type": "pod", "resource_name": pod_name, "namespace": namespace}))
    resource_snapshot = _enrich_pod_snapshot(resource_snapshot)
    resolved_node_name = _first_non_empty(
        node_name,
        ((resource_snapshot or {}).get("spec") or {}).get("nodeName"),
        ((resource_snapshot or {}).get("spec") or {}).get("node_name"),
    )
    current_logs = get_kubernetes_pod_logs.invoke(
        {"namespace": namespace, "pod_name": pod_name, "container": container_name, "lines": lines, "tail": True}
    )
    previous_logs = get_kubernetes_previous_pod_logs.invoke(
        {"namespace": namespace, "pod_name": pod_name, "container": container_name, "lines": lines, "tail": True}
    )

    service_ref = _extract_service_reference_from_logs(current_logs, previous_logs)

    context = {
        "resource_snapshot": resource_snapshot,
        "events_timeline": _json_or_raw(
            get_resource_events_timeline.invoke(
                {"resource_type": "Pod", "resource_name": pod_name, "namespace": namespace, "hours": max(1, minutes // 60)}
            )
        ),
        "pod_logs": {
            "current": {
                "container_name": container_name,
                "lines": lines,
                "content": current_logs,
            },
            "previous": {
                "container_name": container_name,
                "lines": lines,
                "content": previous_logs,
            },
        },
        "node_context": _json_or_raw(diagnose_node_issues.invoke({"node_name": resolved_node_name})) if resolved_node_name else None,
        "service_topology": _json_or_raw(
            trace_service_chain.invoke({"service_name": service_ref["service_name"], "namespace": service_ref["namespace"]})
        )
        if service_ref
        else None,
        "change_context": None,
    }

    owner_workload = (resource_snapshot or {}).get("owner_workload") or {}
    if owner_workload.get("kind") in {"Deployment", "StatefulSet", "ReplicaSet", "DaemonSet"}:
        context["change_context"] = {
            "owner_workload": owner_workload,
        }
    return context


def _collect_node_context(target, scope):
    node_name = target.get("node_name") or target.get("resource_name")
    minutes = int((scope or {}).get("time_window_minutes") or 60)
    return {
        "resource_snapshot": _json_or_raw(describe_kubernetes_resource.invoke({"resource_type": "node", "resource_name": node_name})),
        "events_timeline": _json_or_raw(
            get_resource_events_timeline.invoke(
                {"resource_type": "Node", "resource_name": node_name, "namespace": "default", "hours": max(1, minutes // 60)}
            )
        ),
        "pod_logs": None,
        "node_context": _json_or_raw(diagnose_node_issues.invoke({"node_name": node_name})),
        "service_topology": None,
        "change_context": None,
    }


def _collect_service_context(target, scope):
    namespace = target.get("namespace")
    service_name = target.get("service_name") or target.get("resource_name")
    return {
        "resource_snapshot": _json_or_raw(
            describe_kubernetes_resource.invoke({"resource_type": "service", "resource_name": service_name, "namespace": namespace})
        ),
        "events_timeline": None,
        "pod_logs": None,
        "node_context": None,
        "service_topology": _json_or_raw(trace_service_chain.invoke({"service_name": service_name, "namespace": namespace})),
        "change_context": None,
    }


def _collect_deployment_context(target, scope):
    namespace = target.get("namespace")
    deployment_name = target.get("deployment_name") or target.get("resource_name")
    include_change_context = (scope or {}).get("include_change_context", True)
    result = {
        "resource_snapshot": _json_or_raw(
            describe_kubernetes_resource.invoke({"resource_type": "deployment", "resource_name": deployment_name, "namespace": namespace})
        ),
        "events_timeline": _json_or_raw(
            get_resource_events_timeline.invoke({"resource_type": "Deployment", "resource_name": deployment_name, "namespace": namespace, "hours": 1})
        ),
        "pod_logs": None,
        "node_context": None,
        "service_topology": None,
        "change_context": None,
    }

    if include_change_context:
        history = _json_or_raw(get_deployment_revision_history.invoke({"deployment_name": deployment_name, "namespace": namespace}))
        result["change_context"] = {"deployment_revision_history": history, "revision_diff": None}
        if isinstance(history, dict):
            revisions = history.get("revisions") or []
            if len(revisions) >= 2:
                latest = revisions[0].get("revision")
                previous = revisions[1].get("revision")
                if latest and previous:
                    result["change_context"]["revision_diff"] = _json_or_raw(
                        compare_deployment_revisions.invoke(
                            {
                                "deployment_name": deployment_name,
                                "namespace": namespace,
                                "revision1": previous,
                                "revision2": latest,
                            }
                        )
                    )

    return result


@tool()
def collect_k8s_context_by_target_type(target, collection_scope=None, instance_name=None, instance_id=None, config: RunnableConfig = None):
    """按 Kubernetes 目标类型编排采集上下文。"""
    target = target if isinstance(target, dict) else {}
    scope = collection_scope if isinstance(collection_scope, dict) else {}

    instances = _get_target_instances(config, instance_name=instance_name, instance_id=instance_id)
    if not instances:
        payload = _collect_single_instance_context(target, scope, config)
        return json.dumps(payload, ensure_ascii=False)

    if len(instances) == 1:
        instance_cfg = _build_instance_config(config, instances[0])
        payload = _collect_single_instance_context(target, scope, instance_cfg)
        payload["instance"] = {"id": instances[0].get("id"), "name": instances[0].get("name")}
        return json.dumps(payload, ensure_ascii=False)

    aggregated = []
    for instance in instances:
        instance_cfg = _build_instance_config(config, instance)
        payload = _collect_single_instance_context(target, scope, instance_cfg)
        aggregated.append(
            {
                "instance": {"id": instance.get("id"), "name": instance.get("name")},
                "result": payload,
            }
        )

    payload = {
        "mode": "multi_instance",
        "instances": aggregated,
        "instance_count": len(aggregated),
    }

    return json.dumps(payload, ensure_ascii=False)


@tool()
def build_incident_evidence_package(
    alert,
    target,
    collection_scope=None,
    resource_snapshot=None,
    events_timeline=None,
    pod_logs=None,
    node_context=None,
    service_topology=None,
    change_context=None,
    related_alerts=None,
    collector_summary=None,
    missing_data=None,
    errors=None,
    workflow_context=None,
    config: RunnableConfig = None,
):
    """将采集结果统一包装为 incident evidence package。"""

    def wrap(name, value):
        if isinstance(value, dict) and "status" in value and "data" in value and "error" in value:
            return value
        if isinstance(value, dict) and "__error__" in value:
            return _evidence_block(status="failed", value=None, error=value.get("__error__"))
        if value is None:
            return _evidence_block(status="skipped", value=None, error=None)
        return _evidence_block(value=_json_or_raw(value), status="success", error=None)

    target_obj = _json_or_raw(target) or {}
    missing = list(missing_data or [])
    errs = list(errors or [])

    resource_snapshot_block = wrap("resource_snapshot", resource_snapshot)
    events_timeline_block = wrap("events_timeline", events_timeline)
    pod_logs_block = wrap("pod_logs", pod_logs)
    node_context_block = wrap("node_context", node_context)
    service_topology_block = wrap("service_topology", service_topology)
    change_context_block = wrap("change_context", change_context)
    related_alerts_block = wrap("related_alerts", related_alerts)

    result = {
        "schema_version": "1.0",
        "workflow_context": workflow_context
        or {
            "execution_id": None,
            "trace_id": None,
            "collector_agent": "k8s-data-collector",
            "collected_at": datetime.now(timezone.utc).isoformat(),
        },
        "alert": _json_or_raw(alert) or {},
        "target": target_obj,
        "collection_scope": collection_scope or {},
        "resource_snapshot": resource_snapshot_block,
        "events_timeline": events_timeline_block,
        "pod_logs": pod_logs_block,
        "node_context": node_context_block,
        "service_topology": service_topology_block,
        "change_context": change_context_block,
        "related_alerts": related_alerts_block,
        "collector_summary": collector_summary or {"facts": [], "suspected_directions": []},
        "missing_data": missing,
        "errors": errs,
        "ready_for_analysis": bool(target_obj.get("resolved", False) or (resource_snapshot is not None or events_timeline is not None)),
    }

    if not target_obj.get("resolved", False) and result["resource_snapshot"]["status"] == "failed":
        result["ready_for_analysis"] = False

    resource_type = (target_obj.get("resource_type") or "").lower()
    alert_obj = result["alert"] if isinstance(result["alert"], dict) else {}
    alert_text = json.dumps(alert_obj, ensure_ascii=False).lower()
    is_restart_like = any(keyword in alert_text for keyword in ["restart", "crash", "backoff", "oom", "exit"])

    if resource_type == "pod" and is_restart_like:
        has_logs = pod_logs_block["status"] == "success" and isinstance(pod_logs_block["data"], dict)
        has_snapshot = resource_snapshot_block["status"] == "success"
        has_events = events_timeline_block["status"] == "success"
        has_node = node_context_block["status"] == "success"
        result["ready_for_analysis"] = all([has_snapshot, has_events, has_logs, has_node])

    return json.dumps(result, ensure_ascii=False)
