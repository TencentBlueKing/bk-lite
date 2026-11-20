"""脚本采集挂到已有单键实例：不新建实例，告警和列表按已启用配置圈选。"""

from __future__ import annotations

from django.db.models import Exists, OuterRef, Q

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.models import CollectConfig, Metric, PolicyGroupRule
from apps.monitor.services.custom_script_plugin import is_script_collect_type
from apps.monitor.utils.dimension import normalize_instance_identity
from apps.monitor.utils.instance_id_keys import resolve_monitor_object_instance_id_keys

SCRIPT_ATTACH_UNSUPPORTED = "这类对象暂不支持添加脚本采集。"
SCRIPT_ATTACH_NEED_INSTANCE = "请先接入该对象的实例，再添加脚本采集。"
SCRIPT_IDENTITY_LOCKED = "不能把这份脚本采集改挂到其它实例。"
_IDENTITY_TAG_KEYS = frozenset({"instance_id", "reserved_instance_id"})


def is_script_plugin(plugin) -> bool:
    if plugin is None:
        return False
    if is_script_collect_type(getattr(plugin, "collect_type", None)):
        return True
    return str(getattr(plugin, "template_type", None) or "").casefold() == "script"


def script_template_id(plugin) -> str:
    """点上的 plugin_id 是模板 id。没有模板 id 时不回退到数字主键。"""
    return str(getattr(plugin, "template_id", None) or "").strip()


def is_single_key_instance_object(monitor_object) -> bool:
    """本期只挂 instance_id 单键对象。带 resource_id 或多键的对象不开放。"""
    if monitor_object is None:
        return False
    keys = resolve_monitor_object_instance_id_keys(
        getattr(monitor_object, "instance_id_keys", None),
        level=getattr(monitor_object, "level", "base"),
        object_name=getattr(monitor_object, "name", ""),
    )
    if "resource_id" in keys:
        return False
    return keys == ["instance_id"]


def bind_script_attach_instance_keys(instances) -> None:
    """提交必须带已有实例的存储键。空身份直接失败，不再哈希出新实例。"""
    for instance in instances or []:
        raw = instance.get("storage_instance_key") or instance.get("instance_id")
        identity = normalize_instance_identity(raw)
        instance["storage_instance_key"] = identity["storage_instance_key"]
        instance["instance_id"] = identity["storage_instance_key"]


def _walk_identity_values(node, found: set[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if key in _IDENTITY_TAG_KEYS and value not in (None, ""):
                found.add(str(value).strip())
            else:
                _walk_identity_values(value, found)
    elif isinstance(node, list):
        for item in node:
            _walk_identity_values(item, found)


def assert_script_identity_unchanged(old_content, new_content) -> None:
    """改配置只能改这份脚本，不能把身份写到另一台已有实例上。"""
    old_ids: set[str] = set()
    new_ids: set[str] = set()
    _walk_identity_values(old_content, old_ids)
    _walk_identity_values(new_content, new_ids)
    if not old_ids or not new_ids:
        return
    if not new_ids.issubset(old_ids):
        raise BaseAppException(SCRIPT_IDENTITY_LOCKED)


def exclude_script_only_instances(queryset):
    """下拉不列「只有脚本配置」的存量独立脚本实例。没有配置、或还有原生配置的仍可选。"""
    configs = CollectConfig.objects.filter(monitor_instance_id=OuterRef("pk"))
    native = configs.exclude(collect_type__iexact="script")
    return queryset.annotate(
        _script_attach_has_config=Exists(configs),
        _script_attach_has_native=Exists(native),
    ).filter(Q(_script_attach_has_config=False) | Q(_script_attach_has_native=True))


def configured_instance_ids(monitor_object_id, plugin_id) -> set:
    return set(
        CollectConfig.objects.filter(
            monitor_plugin_id=plugin_id,
            monitor_instance__monitor_object_id=monitor_object_id,
            monitor_instance__is_deleted=False,
        ).values_list("monitor_instance_id", flat=True)
    )


def plugin_filter_membership(monitor_object, plugin):
    """按插件过滤列表的成员。

    单键对象和脚本插件只认 CollectConfig：已配置但还没出点的要出现，
    卸载后不能靠过期点继续留下。多键对象没有任何配置时仍按上报点过滤
    （K8s 这类没有 CollectConfig 的上报实例）。返回 None 表示沿用上报点交集。
    """
    configured = configured_instance_ids(monitor_object.id, plugin.id)
    if is_script_plugin(plugin) or is_single_key_instance_object(monitor_object) or configured:
        return configured
    return None


def script_plugin_status_probe(plugin, instance_id_keys) -> str | None:
    """脚本插件的状态探测用模板 id，不用插件数字主键。"""
    if not is_script_plugin(plugin):
        return None
    keys = [str(key).strip() for key in (instance_id_keys or []) if str(key).strip()] or ["instance_id"]
    labels = ['collect_type="script"']
    template_id = script_template_id(plugin)
    if template_id:
        escaped = template_id.replace("\\", "\\\\").replace('"', '\\"')
        labels.append(f'plugin_id="{escaped}"')
    return f'any({{{", ".join(labels)}}}) by ({", ".join(keys)})'


def script_collect_scope_plugin_ids(policy):
    """脚本策略要与已启用插件求交的插件 id。

    None：不是脚本策略，扫描范围保持策略来源。
    空集合：标明是脚本策略，但无法确定插件，不把整个对象拿去扫无数据。
    """
    from apps.monitor.tasks.utils.policy_multi import query_metric_items

    items = query_metric_items(getattr(policy, "query_condition", None) or {})
    metric_ids = [item.get("metric_id") for item in items if isinstance(item, dict) and item.get("metric_id")]
    if metric_ids:
        script_ids = set()
        saw_metric = False
        for metric in Metric.objects.filter(id__in=metric_ids).select_related("monitor_plugin"):
            saw_metric = True
            if is_script_plugin(metric.monitor_plugin):
                script_ids.add(metric.monitor_plugin_id)
        if saw_metric:
            return script_ids or None
    if str(getattr(policy, "collect_type", "") or "").casefold() != "script":
        return None
    template = getattr(policy, "source_template", None)
    plugin_id = getattr(template, "plugin_id", None) if template is not None else None
    if plugin_id:
        return {plugin_id}
    rule_plugin_id = PolicyGroupRule.objects.filter(policy_id=policy.id).values_list("plugin_id", flat=True).first()
    if rule_plugin_id:
        return {rule_plugin_id}
    return set()


def restrict_script_policy_instances(policy, instances_map, resource_ip_map):
    """无数据扫描与圈选和「该实例已启用该脚本插件」求交。不关闭出圈告警。"""
    plugin_ids = script_collect_scope_plugin_ids(policy)
    if plugin_ids is None:
        return instances_map, resource_ip_map
    if not plugin_ids or not instances_map:
        return {}, {}
    enabled = None
    candidate_ids = list(instances_map)
    for plugin_id in plugin_ids:
        rows = set(
            CollectConfig.objects.filter(
                monitor_plugin_id=plugin_id,
                monitor_instance_id__in=candidate_ids,
            ).values_list("monitor_instance_id", flat=True)
        )
        enabled = rows if enabled is None else enabled & rows
    enabled = enabled or set()
    instances_map = {key: value for key, value in instances_map.items() if key in enabled}
    resource_ip_map = {key: value for key, value in (resource_ip_map or {}).items() if key in instances_map}
    return instances_map, resource_ip_map
