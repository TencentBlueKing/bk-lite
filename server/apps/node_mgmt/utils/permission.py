from django.db.models import Count, F, Q

from apps.core.utils.permission_utils import get_instance_permission_map, get_permission_rules, permission_filter
from apps.core.utils.team_utils import get_current_team
from apps.core.utils.user_group import normalize_user_group_ids
from apps.core.utils.web_utils import WebUtils
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.models.sidecar import ChildConfig, CollectorConfiguration, Node
from apps.rpc.system_mgmt import SystemMgmt


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
    current_team = get_current_team(request)
    user = get_request_user(request)

    if current_team in (None, "") or user is None:
        return {}

    try:
        current_team_int = int(current_team)
    except (TypeError, ValueError):
        return {}

    scope_result = SystemMgmt(is_local_client=True).get_authorized_groups_scoped(
        {
            "username": getattr(user, "username", ""),
            "domain": getattr(user, "domain", "domain.com"),
            "current_team": current_team_int,
            "is_superuser": getattr(user, "is_superuser", False),
        },
        include_children=include_children,
    )
    authorized_groups = scope_result.get("data", []) if isinstance(scope_result, dict) else []
    if not authorized_groups:
        return {}

    permission = get_permission_rules(
        user,
        current_team_int,
        "node_mgmt",
        NodeConstants.MODULE,
        include_children=include_children,
    )
    return permission if isinstance(permission, dict) else {}


def get_request_user(request):
    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", True):
        return user
    return getattr(request, "_force_auth_user", user)


def get_authorized_node_queryset(request, permission=None):
    permission = permission or get_node_permission(request)
    return permission_filter(
        Node,
        permission,
        team_key="nodeorganization__organization__in",
        id_key="id__in",
    )


def get_authorized_collector_configuration_queryset(request, permission=None):
    permission = permission or get_node_permission(request)
    authorized_node_ids = list(get_authorized_node_queryset(request, permission).distinct().values_list("id", flat=True))
    username = getattr(get_request_user(request), "username", "")

    filters = Q()
    if authorized_node_ids:
        filters |= Q(nodes__id__in=authorized_node_ids)
    if username:
        filters |= Q(created_by=username, nodes__isnull=True)

    if not filters:
        return CollectorConfiguration.objects.none()

    return CollectorConfiguration.objects.filter(filters).distinct()


def get_authorized_child_config_queryset(request, permission=None):
    authorized_configs = get_authorized_collector_configuration_queryset(request, permission)
    return ChildConfig.objects.filter(collector_config__in=authorized_configs).distinct()


def get_mutable_collector_configuration_queryset(request, permission=None):
    permission = permission or get_node_permission(request)
    authorized_node_ids = list(get_authorized_node_queryset(request, permission).distinct().values_list("id", flat=True))
    username = getattr(get_request_user(request), "username", "")

    writable_unbound_ids = []
    if username:
        writable_unbound_ids = list(CollectorConfiguration.objects.filter(created_by=username, nodes__isnull=True).values_list("id", flat=True))

    writable_bound_ids = []
    if authorized_node_ids:
        writable_bound_ids = list(
            CollectorConfiguration.objects.annotate(
                total_nodes=Count("nodes", distinct=True),
                authorized_nodes=Count("nodes", filter=Q(nodes__id__in=authorized_node_ids), distinct=True),
            )
            .filter(total_nodes__gt=0, total_nodes=F("authorized_nodes"))
            .values_list("id", flat=True)
        )

    writable_ids = list(dict.fromkeys([*writable_unbound_ids, *writable_bound_ids]))
    if not writable_ids:
        return CollectorConfiguration.objects.none()

    return CollectorConfiguration.objects.filter(id__in=writable_ids).distinct()


def get_mutable_child_config_queryset(request, permission=None):
    writable_configs = get_mutable_collector_configuration_queryset(request, permission)
    return ChildConfig.objects.filter(collector_config__in=writable_configs).distinct()


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


def authorize_collector_configuration_ids(request, config_ids, permission=None):
    normalized_ids = normalize_ids(config_ids)
    if not normalized_ids:
        return None, WebUtils.response_error(error_message="collector_configuration_ids is required")

    configurations = list(CollectorConfiguration.objects.filter(id__in=normalized_ids).distinct())
    configuration_map = {str(config.id): config for config in configurations}
    if any(config_id not in configuration_map for config_id in normalized_ids):
        return None, WebUtils.response_error(error_message="collector configuration does not exist")

    authorized_configurations = list(get_authorized_collector_configuration_queryset(request, permission).filter(id__in=normalized_ids).distinct())
    authorized_map = {str(config.id): config for config in authorized_configurations}
    unauthorized_ids = [config_id for config_id in normalized_ids if config_id not in authorized_map]
    if unauthorized_ids:
        return None, WebUtils.response_403("User does not have permission to operate this configuration")

    return [authorized_map[config_id] for config_id in normalized_ids], None


def authorize_mutable_collector_configuration_ids(request, config_ids, permission=None):
    normalized_ids = normalize_ids(config_ids)
    if not normalized_ids:
        return None, WebUtils.response_error(error_message="collector_configuration_ids is required")

    configurations = list(CollectorConfiguration.objects.filter(id__in=normalized_ids).distinct())
    configuration_map = {str(config.id): config for config in configurations}
    if any(config_id not in configuration_map for config_id in normalized_ids):
        return None, WebUtils.response_error(error_message="collector configuration does not exist")

    writable_configurations = list(get_mutable_collector_configuration_queryset(request, permission).filter(id__in=normalized_ids).distinct())
    writable_map = {str(config.id): config for config in writable_configurations}
    unauthorized_ids = [config_id for config_id in normalized_ids if config_id not in writable_map]
    if unauthorized_ids:
        return None, WebUtils.response_403("User does not have permission to modify this configuration")

    return [writable_map[config_id] for config_id in normalized_ids], None


def authorize_child_config_ids(request, child_config_ids, permission=None):
    normalized_ids = normalize_ids(child_config_ids)
    if not normalized_ids:
        return None, WebUtils.response_error(error_message="child_config_ids is required")

    child_configs = list(ChildConfig.objects.filter(id__in=normalized_ids).select_related("collector_config").distinct())
    child_config_map = {str(config.id): config for config in child_configs}
    if any(config_id not in child_config_map for config_id in normalized_ids):
        return None, WebUtils.response_error(error_message="child config does not exist")

    authorized_child_configs = list(get_authorized_child_config_queryset(request, permission).filter(id__in=normalized_ids).distinct())
    authorized_map = {str(config.id): config for config in authorized_child_configs}
    unauthorized_ids = [config_id for config_id in normalized_ids if config_id not in authorized_map]
    if unauthorized_ids:
        return None, WebUtils.response_403("User does not have permission to operate this child configuration")

    return [authorized_map[config_id] for config_id in normalized_ids], None


def authorize_mutable_child_config_ids(request, child_config_ids, permission=None):
    normalized_ids = normalize_ids(child_config_ids)
    if not normalized_ids:
        return None, WebUtils.response_error(error_message="child_config_ids is required")

    child_configs = list(ChildConfig.objects.filter(id__in=normalized_ids).select_related("collector_config").distinct())
    child_config_map = {str(config.id): config for config in child_configs}
    if any(config_id not in child_config_map for config_id in normalized_ids):
        return None, WebUtils.response_error(error_message="child config does not exist")

    writable_child_configs = list(get_mutable_child_config_queryset(request, permission).filter(id__in=normalized_ids).distinct())
    writable_map = {str(config.id): config for config in writable_child_configs}
    unauthorized_ids = [config_id for config_id in normalized_ids if config_id not in writable_map]
    if unauthorized_ids:
        return None, WebUtils.response_403("User does not have permission to modify this child configuration")

    return [writable_map[config_id] for config_id in normalized_ids], None


def authorize_target_organizations(request, node, organizations):
    target_orgs = normalize_orgs(organizations)
    if not target_orgs:
        return None

    user = get_request_user(request)
    if user is None:
        return WebUtils.response_403("User does not have permission to assign nodes to these organizations")

    if getattr(user, "is_superuser", False):
        return None

    user_group_list = getattr(user, "group_list", []) or []
    user_group_ids = normalize_user_group_ids(user_group_list)
    if not user_group_ids:
        return WebUtils.response_403("User does not have permission to assign nodes to these organizations")

    from apps.system_mgmt.utils.group_utils import GroupUtils
    allowed_orgs = set(GroupUtils.get_group_with_descendants(user_group_ids))

    if not target_orgs.issubset(allowed_orgs):
        return WebUtils.response_403("User does not have permission to assign nodes to these organizations")

    return None
