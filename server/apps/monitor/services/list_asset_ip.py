import yaml
from django.db.models import F

from apps.core.logger import monitor_logger as logger
from apps.monitor.models import CollectConfig
from apps.monitor.services.host_container_asset_ip import ASSET_IP_FACT, _mapped_ip_for_node
from apps.monitor.services.instance_facts import InstanceFactResolver
from apps.node_mgmt.constants.controller import ControllerConstants
from apps.node_mgmt.models.sidecar import ChildConfig, CollectorConfiguration
from apps.node_mgmt.utils.region_display_ip import as_ip, load_region_display_ips

JVM_OBJECT_NAME = "JVM"


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
