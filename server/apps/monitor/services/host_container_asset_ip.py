from django.db.models import F

from apps.core.logger import monitor_logger as logger
from apps.monitor.models import CollectConfig
from apps.monitor.services.host_deployment import HostDeploymentStatus
from apps.node_mgmt.constants.controller import ControllerConstants
from apps.node_mgmt.models.sidecar import ChildConfig
from apps.node_mgmt.utils.region_display_ip import as_ip, load_region_display_ips

ASSET_IP_FACT = "asset.ip"


def fill_missing_host_container_asset_ips(items, monitor_object_name=None):
    """列表期回填 Host 本地采集缺失的 asset.ip，不落库。

    仅走 CollectConfig(Telegraf/host) → ChildConfig → Node → 云区域展示 IP。
    容器节点无可用 node.ip 时用区域 proxy / 平台 IP；普通主机节点仍用 node.ip。
    Host Remote / k8s / 云 resource_ip 不在此路径。
    """
    if monitor_object_name not in (None, "", HostDeploymentStatus.MONITOR_OBJECT_NAME):
        return
    try:
        _fill_missing_host_container_asset_ips(items)
    except Exception as exc:
        logger.exception(
            "event=fill_host_container_asset_ip_failed failed_stage=list_fill error_type=%s item_count=%s",
            type(exc).__name__,
            len(items or []),
        )


def _fill_missing_host_container_asset_ips(items):
    if not items:
        return

    missing_ids = []
    items_by_id = {}
    for item in items:
        instance_id = item.get("instance_id")
        if instance_id in (None, "") or not _missing_asset_ip(item.get("summary_facts")):
            continue
        missing_ids.append(instance_id)
        items_by_id.setdefault(instance_id, []).append(item)
    if not missing_ids:
        return

    config_rows = list(
        CollectConfig.objects.filter(
            monitor_instance_id__in=missing_ids,
            collector=HostDeploymentStatus.COLLECTOR,
            collect_type=HostDeploymentStatus.COLLECT_TYPE,
            is_child=True,
        ).values_list("id", "monitor_instance_id")
    )
    if not config_rows:
        return

    instance_by_config_id = {str(config_id): instance_id for config_id, instance_id in config_rows}
    node_rows = list(
        ChildConfig.objects.filter(id__in=instance_by_config_id.keys())
        .values(
            "id",
            node_id=F("collector_config__nodes__id"),
            node_type=F("collector_config__nodes__node_type"),
            node_ip=F("collector_config__nodes__ip"),
            cloud_region_id=F("collector_config__nodes__cloud_region_id"),
        )
        .order_by("id", "node_id")
    )
    mapped_by_instance = {}
    region_ids = {
        row["cloud_region_id"]
        for row in node_rows
        if str(row.get("node_type") or "") == ControllerConstants.NODE_TYPE_CONTAINER
        and row.get("cloud_region_id") not in (None, "")
        and not as_ip(row.get("node_ip"))
    }
    region_display_ips = load_region_display_ips(region_ids)
    for row in node_rows:
        instance_id = instance_by_config_id.get(str(row["id"]))
        if instance_id in (None, "") or instance_id in mapped_by_instance or row.get("node_id") in (None, ""):
            continue
        mapped = _mapped_ip_for_node(
            row.get("node_type"),
            row.get("node_ip"),
            region_display_ips.get(row.get("cloud_region_id"), ""),
        )
        if mapped:
            mapped_by_instance[instance_id] = mapped

    for instance_id, mapped in mapped_by_instance.items():
        for item in items_by_id.get(instance_id, []):
            facts = dict(item.get("summary_facts") or {})
            facts[ASSET_IP_FACT] = mapped
            item["summary_facts"] = facts


def _missing_asset_ip(facts):
    if not isinstance(facts, dict):
        return True
    return facts.get(ASSET_IP_FACT) in (None, "")


def _mapped_ip_for_node(node_type, node_ip, region_display_ip):
    own_ip = as_ip(node_ip)
    if str(node_type or "") == ControllerConstants.NODE_TYPE_CONTAINER:
        return own_ip or as_ip(region_display_ip)
    return own_ip
