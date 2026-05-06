from apps.core.utils.permission_utils import get_instance_permission_map, get_permission_rules, permission_filter
from apps.core.utils.web_utils import WebUtils
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.models.sidecar import Node


def normalize_ids(values):
    if not values:
        return []
    if not isinstance(values, list):
        values = [values]
    return [str(value) for value in values if value is not None and str(value) != ""]


def normalize_orgs(values):
    if not values:
        return set()
    if not isinstance(values, list):
        values = [values]

    organizations = set()
    for value in values:
        try:
            organizations.add(int(value))
        except (TypeError, ValueError):
            continue
    return organizations


def get_node_permission(request):
    include_children = request.COOKIES.get("include_children", "0") == "1"
    permission = get_permission_rules(
        request.user,
        request.COOKIES.get("current_team"),
        "node_mgmt",
        NodeConstants.MODULE,
        include_children=include_children,
    )
    return permission if isinstance(permission, dict) else {}


def get_authorized_node_queryset(request, permission=None):
    permission = permission or get_node_permission(request)
    return permission_filter(
        Node,
        permission,
        team_key="nodeorganization__organization__in",
        id_key="id__in",
    )


def get_node_organizations(node):
    return {relation.organization for relation in node.nodeorganization_set.all()}


def get_node_permissions(node, permission):
    instance_permission_map = get_instance_permission_map(permission)
    node_id = str(node.id)
    if node_id in instance_permission_map:
        return instance_permission_map[node_id]

    if get_node_organizations(node) & normalize_orgs(permission.get("team", [])):
        return NodeConstants.DEFAULT_PERMISSION

    return []


def add_node_permissions(permission, items):
    instance_permission_map = get_instance_permission_map(permission)
    for node_info in items:
        node_id = str(node_info["id"])
        node_info["permission"] = instance_permission_map.get(node_id, NodeConstants.DEFAULT_PERMISSION)


def authorize_node_ids(request, node_ids, required_permission="Operate"):
    normalized_ids = normalize_ids(node_ids)
    if not normalized_ids:
        return None, WebUtils.response_error(error_message="node_ids is required")

    nodes = list(Node.objects.filter(id__in=normalized_ids).prefetch_related("nodeorganization_set").distinct())
    node_map = {str(node.id): node for node in nodes}
    if any(node_id not in node_map for node_id in normalized_ids):
        return None, WebUtils.response_error(error_message="node does not exist")

    permission = get_node_permission(request)
    unauthorized_ids = [node_id for node_id in normalized_ids if required_permission not in get_node_permissions(node_map[node_id], permission)]
    if unauthorized_ids:
        return None, WebUtils.response_403("User does not have permission to operate this node")

    return [node_map[node_id] for node_id in normalized_ids], None


def authorize_target_organizations(request, node, organizations):
    target_orgs = normalize_orgs(organizations)
    if not target_orgs:
        return None

    permission = get_node_permission(request)
    allowed_orgs = normalize_orgs(permission.get("team", [])) | get_node_organizations(node)
    if not target_orgs.issubset(allowed_orgs):
        return WebUtils.response_403("User does not have permission to assign nodes to these organizations")

    return None
