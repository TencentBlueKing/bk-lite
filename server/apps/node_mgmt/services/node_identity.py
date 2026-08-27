"""Business-logic uniqueness for Node identity: (cloud_region_id, ip).

No database unique constraint is added. Historical duplicate rows are left
untouched; a third create for the same cloud region + IP is still blocked.
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


def resolve_reusable_node_id(cloud_region_id, ip, requested_node_id: str = "") -> str:
    """Return the Node.id to reuse for (cloud_region, ip), or the requested id if the IP is new.

    Historical duplicates are not merged. Creating a third Node is rejected.
    """
    requested = (requested_node_id or "").strip()
    matches = nodes_for_cloud_ip(cloud_region_id, ip)
    if not matches:
        return requested
    match_ids = {node.id for node in matches}
    if requested and requested in match_ids:
        return requested
    if len(matches) == 1:
        return matches[0].id
    raise ValidationAppException(cloud_ip_already_exists_message(normalize_node_ip(ip)))


def bind_existing_cloud_ip_node_ids(cloud_region_id, nodes: list[dict]) -> list[dict]:
    """Copy nodes and bind unique existing (cloud_region, ip) rows onto node_id."""
    assert_unique_ips_in_batch(nodes)
    grouped = _nodes_by_ip(cloud_region_id, (node.get("ip") for node in nodes))
    bound = []
    for node in nodes:
        item = dict(node)
        ip = normalize_node_ip(item.get("ip"))
        item["ip"] = ip
        requested = (item.get("node_id") or "").strip()
        matches = grouped.get(ip, [])
        if not matches:
            if requested:
                item["node_id"] = requested
            bound.append(item)
            continue
        match_ids = {existing.id for existing in matches}
        if requested and requested in match_ids:
            item["node_id"] = requested
        elif len(matches) == 1:
            item["node_id"] = matches[0].id
        else:
            raise ValidationAppException(cloud_ip_already_exists_message(ip))
        bound.append(item)
    return bound


def resolve_sidecar_create_node(*, reported_node_id: str, cloud_region_id, ip: str, lock: bool = True) -> Node | None:
    """Return an existing Node to attach to, or None if a new row may be created.

    Caller must already know that no Node exists for reported_node_id.
    """
    matches = nodes_for_cloud_ip(cloud_region_id, ip, lock=lock)
    if not matches:
        return None
    match_ids = {node.id for node in matches}
    if reported_node_id in match_ids:
        return next(node for node in matches if node.id == reported_node_id)
    if len(matches) == 1:
        return matches[0]
    raise ValidationAppException(cloud_ip_already_exists_message(normalize_node_ip(ip)))
