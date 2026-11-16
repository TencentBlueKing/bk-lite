import yaml
from django.db import connection
from django.db.models import F, Q
from django.db.models.fields.json import KeyTextTransform

from apps.core.logger import monitor_logger as logger
from apps.monitor.models import CollectConfig, MonitorInstance
from apps.monitor.services.host_container_asset_ip import ASSET_IP_FACT, _mapped_ip_for_node
from apps.monitor.services.instance_facts import InstanceFactResolver
from apps.monitor.utils.alert_name_variables import summary_facts_with_model_ip
from apps.node_mgmt.constants.controller import ControllerConstants
from apps.node_mgmt.models.sidecar import ChildConfig, CollectorConfiguration
from apps.node_mgmt.utils.region_display_ip import as_ip, load_region_display_ips

# 常见回环 / 未指定地址。127.0.0.0/8 的其余地址靠 JSON 文本前缀再经 is_placeholder_ip 确认。
_PLACEHOLDER_IPS = ("127.0.0.1", "::1", "0.0.0.0", "::", "0:0:0:0:0:0:0:1", "0:0:0:0:0:0:0:0")

JVM_OBJECT_NAME = "JVM"


def backfill_resolved_asset_ips(monitor_object_id, monitor_object_name=None, instance_ids=None):
    """把列表已经能算出的 IP 写回摘要，只写占位地址和空 JVM。

    写一次后告警 ${resource_ip}、筛选和搜索与列表读到同一个值。已是普通 IP 的实例不改。
    """
    if monitor_object_id in (None, ""):
        return 0
    try:
        return _backfill_resolved_asset_ips(monitor_object_id, monitor_object_name, instance_ids)
    except Exception as exc:
        logger.exception(
            "event=backfill_resolved_asset_ip_failed failed_stage=backfill error_type=%s object_id=%s",
            type(exc).__name__,
            monitor_object_id,
        )
        return 0


def backfill_resolved_asset_ips_for_instances(instances):
    """按实例所属对象回填。通知发送时实例可能跨对象。"""
    grouped = {}
    for instance in instances or []:
        monitor_object = getattr(instance, "monitor_object", None)
        object_name = getattr(monitor_object, "name", None)
        object_id = getattr(instance, "monitor_object_id", None)
        if object_id in (None, "") or getattr(instance, "id", None) in (None, ""):
            continue
        grouped.setdefault((object_id, object_name), []).append(instance.id)
    updated = 0
    for (object_id, object_name), instance_ids in grouped.items():
        updated += backfill_resolved_asset_ips(object_id, object_name, instance_ids)
    return updated


def _backfill_resolved_asset_ips(monitor_object_id, monitor_object_name, instance_ids):
    instances = list(_instances_needing_asset_ip(monitor_object_id, monitor_object_name, instance_ids))
    if not instances:
        return 0
    items = []
    by_id = {}
    for instance in instances:
        items.append(
            {
                "instance_id": instance.id,
                "summary_facts": summary_facts_with_model_ip(instance.summary_facts, instance.ip),
            }
        )
        by_id[instance.id] = instance
    _fill_jvm_asset_ips(items, monitor_object_name)
    _replace_placeholder_with_single_collector_node(items)

    changed = []
    for item in items:
        instance = by_id[item["instance_id"]]
        new_ip = _asset_ip(item.get("summary_facts"))
        old_ip = _asset_ip(instance.summary_facts)
        if not new_ip or InstanceFactResolver.is_placeholder_ip(new_ip) or new_ip == old_ip:
            continue
        facts = dict(instance.summary_facts or {})
        facts[ASSET_IP_FACT] = new_ip
        instance.summary_facts = facts
        changed.append(instance)
    for instance in changed:
        instance.save(update_fields=["summary_facts"])
    return len(changed)


def _instances_needing_asset_ip(monitor_object_id, monitor_object_name, instance_ids):
    queryset = MonitorInstance.objects.filter(monitor_object_id=monitor_object_id, is_deleted=False).only("id", "ip", "summary_facts")
    if instance_ids is not None:
        queryset = queryset.filter(id__in=list(instance_ids))
    # SQLite 的 JSON 查询会把比较值再套一层 JSON_EXTRACT，127.0.0.1 会被当成非法 JSON。
    if connection.vendor == "sqlite":
        return [instance for instance in queryset.iterator() if _row_needs_backfill(instance, monitor_object_name)]
    queryset = queryset.annotate(_asset_ip=KeyTextTransform(ASSET_IP_FACT, "summary_facts"))
    placeholder_fact = Q(_asset_ip__startswith="127.") | Q(_asset_ip__in=_PLACEHOLDER_IPS)
    empty_fact = Q(_asset_ip__isnull=True) | Q(_asset_ip="")
    placeholder_model = Q(ip__in=_PLACEHOLDER_IPS)
    needs_resolution = placeholder_fact | (empty_fact & placeholder_model)
    if monitor_object_name == JVM_OBJECT_NAME:
        needs_resolution = needs_resolution | (empty_fact & (Q(ip__isnull=True) | placeholder_model))
    return queryset.filter(needs_resolution)


def _row_needs_backfill(instance, monitor_object_name):
    fact = _asset_ip(instance.summary_facts)
    model_is_placeholder = InstanceFactResolver.is_placeholder_ip(instance.ip)
    if InstanceFactResolver.is_placeholder_ip(fact):
        return True
    if fact:
        return False
    if model_is_placeholder:
        return True
    model_missing = instance.ip in (None, "")
    return monitor_object_name == JVM_OBJECT_NAME and model_missing


def present_list_asset_ips(items, monitor_object_name=None):
    """列表响应里补展示用 IP，不落库。

    存量 JVM 从已保存的 jmxUrl 解析；回环或未指定地址在恰好一个采集节点时改显示该节点 IP。
    """
    if not items:
        return
    try:
        _fill_jvm_asset_ips(items, monitor_object_name)
        _replace_placeholder_with_single_collector_node(items)
    except Exception as exc:
        logger.exception(
            "event=present_list_asset_ip_failed failed_stage=list_fill error_type=%s item_count=%s",
            type(exc).__name__,
            len(items or []),
        )


def _fill_jvm_asset_ips(items, monitor_object_name):
    if monitor_object_name != JVM_OBJECT_NAME:
        return
    pending = {}
    for item in items:
        instance_id = item.get("instance_id")
        if instance_id in (None, "") or not _missing_asset_ip(item.get("summary_facts")):
            continue
        pending.setdefault(instance_id, []).append(item)
    if not pending:
        return

    config_rows = list(
        CollectConfig.objects.filter(
            monitor_instance_id__in=list(pending),
            is_child=False,
            file_type="yaml",
        ).values_list("id", "monitor_instance_id")
    )
    if not config_rows:
        return
    instance_by_config = {str(config_id): instance_id for config_id, instance_id in config_rows}
    templates = CollectorConfiguration.objects.filter(id__in=instance_by_config).values_list("id", "config_template")
    resolved = {}
    for config_id, content in templates:
        instance_id = instance_by_config.get(str(config_id))
        if instance_id in (None, "") or instance_id in resolved:
            continue
        parsed = _ip_from_jmx_url(_jmx_url(content))
        if parsed:
            resolved[instance_id] = parsed
    for instance_id, ip in resolved.items():
        for item in pending.get(instance_id, []):
            _set_asset_ip(item, ip)


def _replace_placeholder_with_single_collector_node(items):
    pending = {}
    for item in items:
        instance_id = item.get("instance_id")
        current = _asset_ip(item.get("summary_facts"))
        if instance_id in (None, "") or not InstanceFactResolver.is_placeholder_ip(current):
            continue
        pending.setdefault(instance_id, []).append(item)
    if not pending:
        return

    node_ips = _single_collector_node_ips(list(pending))
    for instance_id, ip in node_ips.items():
        if InstanceFactResolver.is_placeholder_ip(ip):
            continue
        for item in pending.get(instance_id, []):
            _set_asset_ip(item, ip)


def _single_collector_node_ips(instance_ids):
    configs = list(CollectConfig.objects.filter(monitor_instance_id__in=instance_ids).values_list("id", "monitor_instance_id", "is_child"))
    if not configs:
        return {}
    instance_by_config = {}
    child_ids = []
    base_ids = []
    for config_id, instance_id, is_child in configs:
        instance_by_config[str(config_id)] = instance_id
        if is_child:
            child_ids.append(config_id)
        else:
            base_ids.append(config_id)

    rows = []
    if child_ids:
        rows.extend(
            ChildConfig.objects.filter(id__in=child_ids).values(
                "id",
                node_id=F("collector_config__nodes__id"),
                node_type=F("collector_config__nodes__node_type"),
                node_ip=F("collector_config__nodes__ip"),
                cloud_region_id=F("collector_config__nodes__cloud_region_id"),
            )
        )
    if base_ids:
        rows.extend(
            CollectorConfiguration.objects.filter(id__in=base_ids).values(
                "id",
                node_id=F("nodes__id"),
                node_type=F("nodes__node_type"),
                node_ip=F("nodes__ip"),
                cloud_region_id=F("nodes__cloud_region_id"),
            )
        )

    region_ids = {
        row["cloud_region_id"]
        for row in rows
        if str(row.get("node_type") or "") == ControllerConstants.NODE_TYPE_CONTAINER
        and row.get("cloud_region_id") not in (None, "")
        and not as_ip(row.get("node_ip"))
    }
    region_display_ips = load_region_display_ips(region_ids)
    ips_by_instance = {}
    for row in rows:
        instance_id = instance_by_config.get(str(row["id"]))
        if instance_id in (None, "") or row.get("node_id") in (None, ""):
            continue
        mapped = _mapped_ip_for_node(
            row.get("node_type"),
            row.get("node_ip"),
            region_display_ips.get(row.get("cloud_region_id"), ""),
        )
        if mapped:
            ips_by_instance.setdefault(instance_id, set()).add(mapped)
    return {instance_id: next(iter(ips)) for instance_id, ips in ips_by_instance.items() if len(ips) == 1}


def _jmx_url(content):
    if not content:
        return None
    try:
        parsed = yaml.safe_load(content)
    except yaml.YAMLError:
        return None
    if not isinstance(parsed, dict):
        return None
    value = parsed.get("jmxUrl")
    if value in (None, ""):
        return None
    return str(value)


def _ip_from_jmx_url(raw_value):
    if raw_value in (None, ""):
        return None
    return InstanceFactResolver._normalize(raw_value, "ip")


def _asset_ip(facts):
    if not isinstance(facts, dict):
        return None
    value = facts.get(ASSET_IP_FACT)
    if value in (None, ""):
        return None
    return value


def _missing_asset_ip(facts):
    return _asset_ip(facts) in (None, "")


def _set_asset_ip(item, ip):
    facts = dict(item.get("summary_facts") or {})
    facts[ASSET_IP_FACT] = ip
    item["summary_facts"] = facts
