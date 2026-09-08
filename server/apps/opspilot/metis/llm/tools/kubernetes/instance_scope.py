"""Kubernetes 多实例路由：定点取证必选实例，扫描类可扇出。"""

from __future__ import annotations

import copy
import json

from langchain_core.runnables import RunnableConfig

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.metis.llm.tools.kubernetes.connection import get_kubernetes_instances_from_configurable, resolve_kubernetes_instance

# LangGraph configurable 含 callback/accumulator 等带锁对象，禁止 deepcopy 整份 config。
_INSTANCE_BIND_KEYS = (
    "kubernetes_instances",
    "kubeconfig_data",
    "instance_name",
    "instance_id",
)


def _configurable(config: RunnableConfig | None) -> dict:
    if not config:
        return {}
    raw = config.get("configurable") or {}
    return raw if isinstance(raw, dict) else {}


def _instance_bind_configurable(config: RunnableConfig | None) -> dict:
    source = _configurable(config)
    bound = {}
    for key in _INSTANCE_BIND_KEYS:
        if key not in source:
            continue
        value = source[key]
        bound[key] = copy.deepcopy(value) if key == "kubernetes_instances" else value
    return bound


def configured_instances(config: RunnableConfig | None) -> list[dict]:
    return get_kubernetes_instances_from_configurable(_configurable(config))


def instance_display_names(instances: list[dict]) -> list[str]:
    names = []
    for item in instances or []:
        name = item.get("name")
        if name:
            names.append(str(name))
    return names


def bind_instance_config(config: RunnableConfig | None, instance: dict) -> dict:
    configurable = _instance_bind_configurable(config)
    configurable["instance_id"] = instance.get("id")
    configurable["instance_name"] = instance.get("name")
    if instance.get("kubeconfig_data"):
        configurable["kubeconfig_data"] = instance.get("kubeconfig_data")
    return {"configurable": configurable}


def bind_instance_name(config: RunnableConfig | None, instance_name=None, instance_id=None) -> dict:
    if not instance_name and not instance_id:
        return config or {}
    instances = configured_instances(config)
    if not instances:
        configurable = _instance_bind_configurable(config)
        if instance_name:
            configurable["instance_name"] = instance_name
        if instance_id:
            configurable["instance_id"] = instance_id
        return {"configurable": configurable}
    instance = resolve_kubernetes_instance(instances, instance_name=instance_name, instance_id=instance_id)
    return bind_instance_config(config, instance)


def _already_bound(config: RunnableConfig | None) -> bool:
    configurable = _configurable(config)
    return bool(configurable.get("instance_name") or configurable.get("instance_id"))


def point_instance_error(config: RunnableConfig | None, instance_name=None) -> str | None:
    """定点取证：多实例且未指定/未绑定实例时返回错误 JSON。"""
    if instance_name or _already_bound(config):
        return None
    instances = configured_instances(config)
    if len(instances) <= 1:
        return None
    names = "、".join(instance_display_names(instances)) or "未命名"
    return json.dumps(
        {
            "error": f"已配置多个 Kubernetes 实例（{names}），请指定 instance_name",
            "instance_names": instance_display_names(instances),
        },
        ensure_ascii=False,
    )


_UNKNOWN_INSTANCE_TEMPLATE = "event=k8s_instance_name_ignored requested=%s bound=%s"


def bind_known_or_keep_bound(config: RunnableConfig | None, instance_name=None) -> tuple[dict | None, str | None]:
    """绑定指定实例；名称对不上时沿用已绑定或唯一实例（LLM 常把 Pod 名填进 instance_name）。"""
    if not instance_name:
        return config or {}, None
    try:
        return bind_instance_name(config, instance_name=instance_name), None
    except ValueError as exc:
        bound_name = str(_configurable(config).get("instance_name") or _configurable(config).get("instance_id") or "-")
        if _already_bound(config):
            logger.debug(_UNKNOWN_INSTANCE_TEMPLATE, instance_name, bound_name)
            return config or {}, None
        instances = configured_instances(config)
        if len(instances) == 1:
            logger.debug(_UNKNOWN_INSTANCE_TEMPLATE, instance_name, instances[0].get("name") or "-")
            return bind_instance_config(config, instances[0]), None
        return None, json.dumps({"error": str(exc)}, ensure_ascii=False)


def prepare_point_instance(config: RunnableConfig | None, instance_name=None) -> tuple[dict | None, str | None]:
    """返回 (绑定后的 config, 错误 JSON)。错误非空时不要继续调用集群 API。"""
    error = point_instance_error(config, instance_name)
    if error:
        return None, error
    return bind_known_or_keep_bound(config, instance_name)


def scan_instances(config: RunnableConfig | None, instance_name=None) -> list[dict] | None:
    """扫描范围。返回 None 表示沿用当前 config（单实例或已绑定）；返回列表则需扇出。"""
    if instance_name:
        return None
    if _already_bound(config):
        return None
    instances = configured_instances(config)
    if len(instances) <= 1:
        return None
    return instances


def wrap_scan_payload(cluster_name: str, raw: str) -> dict:
    payload = raw
    if isinstance(raw, str):
        text = raw.strip()
        if text and text[0] in "{[":
            try:
                payload = json.loads(text)
            except Exception:
                payload = {"raw": raw}
        else:
            payload = {"raw": raw}
    if isinstance(payload, dict) and payload.get("error"):
        return {"cluster": cluster_name, "error": payload.get("error")}
    if isinstance(payload, list):
        return {"cluster": cluster_name, "items": payload}
    if isinstance(payload, dict):
        wrapped = dict(payload)
        wrapped["cluster"] = cluster_name
        return wrapped
    return {"cluster": cluster_name, "items": payload}


def run_scan_tool(config: RunnableConfig | None, instance_name, run_single) -> str:
    """run_single(bound_config) -> JSON/文本。多实例未指定时扇出；坏实例记 error。"""
    if instance_name:
        bound, error = bind_known_or_keep_bound(config, instance_name)
        if error:
            return error
        return run_single(bound)

    scoped = scan_instances(config, instance_name=None)
    if scoped is None:
        return run_single(config)

    results = []
    for instance in scoped:
        name = instance.get("name") or instance.get("id") or "unknown"
        bound = bind_instance_config(config, instance)
        try:
            results.append(wrap_scan_payload(str(name), run_single(bound)))
        except Exception as exc:
            results.append({"cluster": str(name), "error": str(exc).strip() or type(exc).__name__})
    return json.dumps({"mode": "multi_instance", "instances": results}, ensure_ascii=False)


def route_alert_cluster(cluster, config: RunnableConfig | None) -> tuple[dict | None, dict]:
    """按告警集群名绑定实例。返回 (bound_config_or_None, extra_fields_for_target)。"""
    extra = {}
    instances = configured_instances(config)
    if not instances:
        return config or {}, extra

    names = instance_display_names(instances)
    names_text = "、".join(names) if names else "未命名"

    if len(instances) == 1:
        instance = instances[0]
        extra["instance_name"] = instance.get("name")
        extra["instance_id"] = instance.get("id")
        cluster_text = str(cluster).strip() if cluster not in (None, "", [], {}) else ""
        if cluster_text:
            try:
                resolve_kubernetes_instance(instances, instance_name=cluster_text)
            except ValueError:
                extra["cluster_mismatch"] = f"告警集群 {cluster_text} 与唯一实例 {instance.get('name')} 不一致"
        return bind_instance_config(config, instance), extra

    cluster_text = str(cluster).strip() if cluster not in (None, "", [], {}) else ""
    if not cluster_text:
        extra["route_error"] = f"告警未提供集群标识，已配置多个实例，无法路由。已配置实例: {names_text}"
        extra["instance_names"] = names
        return None, extra
    try:
        instance = resolve_kubernetes_instance(instances, instance_name=cluster_text)
    except ValueError:
        extra["route_error"] = f"告警集群 {cluster_text} 未绑定实例。已配置实例: {names_text}"
        extra["instance_names"] = names
        return None, extra
    extra["instance_name"] = instance.get("name")
    extra["instance_id"] = instance.get("id")
    return bind_instance_config(config, instance), extra
