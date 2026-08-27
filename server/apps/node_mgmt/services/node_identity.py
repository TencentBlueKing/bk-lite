"""Business-logic uniqueness for Node identity: (cloud_region_id, ip).

No database unique constraint is added. Historical duplicate rows are left
untouched; a later create for the same cloud region + IP is still blocked.
"""

from collections import defaultdict

from django.db.models import QuerySet

from apps.core.exceptions.base_app_exception import ValidationAppException
from apps.node_mgmt.constants.database import CloudRegionConstants
from apps.node_mgmt.models.sidecar import Node


def normalize_node_ip(ip) -> str:
    if ip is None:
        return ""
    return str(ip).strip()


def cloud_ip_already_exists_message(ip: str) -> str:
    return f"IP {ip} already exists in this cloud region"


def duplicate_ip_in_batch_message(ip: str) -> str:
    return f"IP {ip} is duplicated in this request"


def default_cloud_region_id(cloud_region_id) -> int:
    if cloud_region_id in (None, ""):
        return CloudRegionConstants.DEFAULT_CLOUD_REGION_ID
    return int(cloud_region_id)


def nodes_for_cloud_ip(cloud_region_id, ip, *, lock: bool = False) -> list[Node]:
    ip_value = normalize_node_ip(ip)
    if not ip_value:
        return []
    qs: QuerySet = Node.objects.filter(
        cloud_region_id=default_cloud_region_id(cloud_region_id),
        ip=ip_value,
    ).order_by("id")
    if lock:
        qs = qs.select_for_update()
    return list(qs)


def first_duplicate_ip(ips) -> str | None:
    seen: set[str] = set()
    for ip in ips:
        value = normalize_node_ip(ip)
        if not value:
            continue
        if value in seen:
            return value
        seen.add(value)
    return None


def assert_unique_ips_in_batch(nodes) -> None:
    duplicate = first_duplicate_ip(node.get("ip") for node in nodes)
    if duplicate:
        raise ValidationAppException(duplicate_ip_in_batch_message(duplicate))


def _nodes_by_ip(cloud_region_id, ips) -> dict[str, list[Node]]:
    normalized = [normalize_node_ip(ip) for ip in ips]
    normalized = [ip for ip in normalized if ip]
    grouped: dict[str, list[Node]] = defaultdict(list)
    if not normalized:
        return grouped
    for node in Node.objects.filter(
        cloud_region_id=default_cloud_region_id(cloud_region_id),
        ip__in=normalized,
    ).order_by("id"):
        grouped[node.ip].append(node)
    return grouped


def assert_cloud_ip_available(cloud_region_id, ip, *, lock: bool = False) -> None:
    matches = nodes_for_cloud_ip(cloud_region_id, ip, lock=lock)
    if matches:
        raise ValidationAppException(cloud_ip_already_exists_message(normalize_node_ip(ip)))


def assert_cloud_ips_available(cloud_region_id, nodes: list[dict]) -> None:
    """Reject batch-duplicate IPs and IPs already occupied in this cloud region."""
    assert_unique_ips_in_batch(nodes)
    grouped = _nodes_by_ip(cloud_region_id, (node.get("ip") for node in nodes))
    for node in nodes:
        ip = normalize_node_ip(node.get("ip"))
        if ip and grouped.get(ip):
            raise ValidationAppException(cloud_ip_already_exists_message(ip))
