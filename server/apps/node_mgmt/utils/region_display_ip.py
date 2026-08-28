import ipaddress
from urllib.parse import urlsplit

from apps.node_mgmt.constants.database import EnvVariableConstants
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.models.cloud_region import CloudRegion
from apps.node_mgmt.services.cloudregion import RegionService


def as_ip(raw_value):
    """把地址规整为 IP；域名或无法解析的值返回 None。"""
    value = str(raw_value or "").strip()
    if not value:
        return None
    for candidate in value.split(","):
        candidate = candidate.strip()
        try:
            return str(ipaddress.ip_address(candidate.strip("[]")))
        except ValueError:
            try:
                parsed = urlsplit(candidate if "://" in candidate else f"//{candidate}")
                return str(ipaddress.ip_address((parsed.hostname or "").strip("[]")))
            except ValueError:
                continue
    return None


def resolve_region_display_ip(proxy_address, sidecar_proxy_address="", node_server_url=""):
    """云区域展示 IP：proxy_address → PROXY_ADDRESS → NODE_SERVER_URL host。

    每级只有规整后的 IP 才采用；域名视为不可用并继续回退。
    """
    for candidate in (proxy_address, sidecar_proxy_address, node_server_url):
        mapped = as_ip(candidate)
        if mapped:
            return mapped
    return None


def load_region_display_ips(cloud_region_ids):
    """批量解析云区域展示 IP，返回 {region_id: ip_or_empty}。"""
    region_ids = {region_id for region_id in cloud_region_ids if region_id not in (None, "")}
    if not region_ids:
        return {}

    proxy_by_region = dict(CloudRegion.objects.filter(id__in=region_ids).values_list("id", "proxy_address"))
    env_by_region = RegionService.get_cloud_regions_envconfig(region_ids)
    display_ips = {}
    for region_id in region_ids:
        env = env_by_region.get(region_id) or {}
        mapped = resolve_region_display_ip(
            proxy_by_region.get(region_id, ""),
            env.get(EnvVariableConstants.PROXY_ADDRESS_KEY, ""),
            env.get(NodeConstants.SERVER_URL_KEY, ""),
        )
        display_ips[region_id] = mapped or ""
    return display_ips
