"""Kubernetes 告警驱动数据采集编排工具。"""

import copy
import json
import re
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


def _extract_labels(alert):
    labels = alert.get("labels") or {}
    return labels if isinstance(labels, dict) else {}


@tool()
def normalize_alert_event(alert_payload, config: RunnableConfig = None):
    """标准化 workflow 告警输入结构。"""
    payload = alert_payload if isinstance(alert_payload, dict) else {}
    labels = payload.get("labels") if isinstance(payload.get("labels"), dict) else {}
    annotations = payload.get("annotations") if isinstance(payload.get("annotations"), dict) else {}

    normalized = {
        "source": payload.get("source") or "unknown",
        "alert_id": payload.get("alert_id") or payload.get("id") or "",
        "title": payload.get("title") or payload.get("name") or "",
        "message": payload.get("message") or payload.get("summary") or "",
        "severity": payload.get("severity") or payload.get("level") or "unknown",
        "status": payload.get("status") or "unknown",
        "firing_time": payload.get("firing_time") or payload.get("startsAt") or payload.get("starts_at"),
        "labels": labels,
        "annotations": annotations,
    }
    return json.dumps(normalized, ensure_ascii=False)


@tool()
def resolve_k8s_target_from_alert(normalized_alert, config: RunnableConfig = None):
    """从标准化告警中解析 Kubernetes 目标对象。"""
    alert = normalized_alert if isinstance(normalized_alert, dict) else {}
    labels = _extract_labels(alert)

    target = {
        "cluster": labels.get("cluster") or labels.get("cluster_id"),
        "namespace": labels.get("namespace"),
        "resource_type": None,
        "resource_name": None,
        "pod_name": labels.get("pod"),
        "container_name": labels.get("container"),
        "node_name": labels.get("node"),
        "deployment_name": labels.get("deployment"),
        "service_name": labels.get("service") or labels.get("service_name"),
        "resolved": False,
        "missing_data": [],
        "reason": None,
    }

    if target["pod_name"]:
        target["resource_type"] = "pod"
        target["resource_name"] = target["pod_name"]
    elif target["node_name"]:
        target["resource_type"] = "node"
        target["resource_name"] = target["node_name"]
    elif target["service_name"] and target["namespace"]:
        target["resource_type"] = "service"
        target["resource_name"] = target["service_name"]
    elif target["deployment_name"] and target["namespace"]:
        target["resource_type"] = "deployment"
        target["resource_name"] = target["deployment_name"]

    if target["resource_type"] and target["resource_name"]:
        target["resolved"] = True
    else:
        target["reason"] = "Missing resource identifier needed to resolve Kubernetes target"
        target["missing_data"].append("resource_type_or_name")

    return json.dumps(target, ensure_ascii=False)


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
