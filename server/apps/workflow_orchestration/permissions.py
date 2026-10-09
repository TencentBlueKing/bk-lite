from __future__ import annotations

from dataclasses import dataclass

from django.db.models import Q, QuerySet

from apps.core.constants import DEFAULT_PERMISSION
from apps.core.utils.permission_utils import get_instance_permission_map, get_permission_rules
from apps.core.utils.viewset_utils import AuthViewSet, build_json_membership_query

APP_NAME = "workflow-orchestration"
PERMISSION_KEY = "workflow"
_CACHE_ATTRIBUTE = "_workflow_orchestration_permission_scope"


def _normalized_ids(values) -> set[str]:
    result = set()
    for value in values or []:
        if isinstance(value, dict):
            value = value.get("id")
        if value not in (None, ""):
            result.add(str(value))
    return result


@dataclass(frozen=True)
class WorkflowPermissionScope:
    organization_ids: set[str]
    team_rule_ids: set[str]
    instance_permissions: dict[str, list[str]]


def _scope(request, current_team: int) -> WorkflowPermissionScope:
    cached = getattr(request, _CACHE_ATTRIBUTE, None)
    if cached is not None and cached[0] == current_team:
        return cached[1]

    organization_ids = {str(current_team)}
    include_children = request.COOKIES.get("include_children", "0") == "1"
    if include_children:
        child_ids = AuthViewSet.extract_child_group_ids(
            getattr(request.user, "group_tree", []),
            current_team,
        )
        organization_ids.update(_normalized_ids(child_ids))

    rules = get_permission_rules(
        request.user,
        current_team,
        APP_NAME,
        PERMISSION_KEY,
        include_children,
    )
    if not isinstance(rules, dict):
        rules = {}
    scope = WorkflowPermissionScope(
        organization_ids=organization_ids,
        team_rule_ids=_normalized_ids(rules.get("team")),
        instance_permissions=get_instance_permission_map(rules),
    )
    setattr(request, _CACHE_ATTRIBUTE, (current_team, scope))
    return scope


def filter_workflow_queryset(
    request,
    queryset: QuerySet,
    current_team: int,
    *,
    require_operate: bool = False,
) -> QuerySet:
    """Apply organization and workflow-instance data scope, failing closed."""

    if getattr(request.user, "is_superuser", False):
        return queryset.filter(build_json_membership_query(queryset, "team", [current_team]))

    scope = _scope(request, current_team)
    organization_query = build_json_membership_query(queryset, "team", scope.organization_ids)

    permitted_instances = [
        instance_id
        for instance_id, permissions in scope.instance_permissions.items()
        if ("Operate" if require_operate else "View") in permissions or (not require_operate and "Operate" in permissions)
    ]
    permission_query = Q(pk__in=permitted_instances)
    if scope.team_rule_ids:
        permission_query |= build_json_membership_query(queryset, "team", scope.team_rule_ids)
    return queryset.filter(organization_query & permission_query)


def workflow_permissions(request, workflow, current_team: int | None = None) -> list[str]:
    if request is None:
        return []
    if getattr(request.user, "is_superuser", False):
        return list(DEFAULT_PERMISSION)
    if current_team is None:
        try:
            current_team = int(request.COOKIES.get("current_team"))
        except (TypeError, ValueError):
            return []
    scope = _scope(request, current_team)
    workflow_teams = _normalized_ids(getattr(workflow, "team", []))
    if workflow_teams & scope.team_rule_ids:
        return list(DEFAULT_PERMISSION)
    return list(scope.instance_permissions.get(str(workflow.pk), []))
