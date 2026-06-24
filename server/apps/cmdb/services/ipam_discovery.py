# -- coding: utf-8 --
"""IP 发现采集 server 端：选子网范围推导、NATS 下发 payload、回调回写。规格 §13。"""
import ipaddress
from apps.cmdb.constants.constants import INSTANCE
from apps.cmdb.graph.drivers.graph_client import GraphClient

DEFAULT_PORTS = [22, 80, 443, 3389]


def _derive_targets(address: str, mask: str, gateway: str = "") -> list:
    try:
        net = ipaddress.ip_network(f"{str(address).strip()}/{str(mask).strip()}", strict=False)
    except (ValueError, TypeError):
        return []
    hosts = [str(ip) for ip in net.hosts()]
    gw = str(gateway or "").strip()
    if gw in hosts:
        hosts.remove(gw)
    return hosts


def _load_subnets_by_ids(subnet_ids: list) -> list:
    ids = [int(i) for i in subnet_ids]
    with GraphClient() as ag:
        rows, _ = ag.query_entity(INSTANCE, [
            {"field": "model_id", "type": "str=", "value": "subnet"},
            {"field": "id", "type": "id[]", "value": ids}])
    return rows or []


def build_scan_payload(subnet_ids: list, scan_method: str = "icmp", ports=None) -> dict:
    targets = []
    for sn in _load_subnets_by_ids(subnet_ids):
        targets.extend(_derive_targets(sn.get("subnet_address"), sn.get("subnet_mask"), sn.get("gateway")))
    return {
        "model_id": "ip",
        "scan_method": (scan_method or "icmp").lower(),
        "ports": list(ports) if ports else DEFAULT_PORTS,
        "targets": targets,
        "callback_subject": "receive_ip_discovery_result",
    }
