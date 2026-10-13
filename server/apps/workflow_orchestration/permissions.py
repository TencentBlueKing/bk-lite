from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from django.contrib.auth import get_user_model
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


def _scope_for_user(user, current_team: int, *, include_children: bool = False) -> WorkflowPermissionScope:
    organization_ids = {str(current_team)}
    if include_children:
        child_ids = AuthViewSet.extract_child_group_ids(
            getattr(user, "group_tree", []),
            current_team,
        )
        organization_ids.update(_normalized_ids(child_ids))

    rules = get_permission_rules(
        user,
        current_team,
        APP_NAME,
        PERMISSION_KEY,
        include_children,
    )
    if not isinstance(rules, dict):
        rules = {}
    return WorkflowPermissionScope(
        organization_ids=organization_ids,
        team_rule_ids=_normalized_ids(rules.get("team")),
        instance_permissions=get_instance_permission_map(rules),
    )


def _scope(request, current_team: int) -> WorkflowPermissionScope:
    cached = getattr(request, _CACHE_ATTRIBUTE, None)
    if cached is not None and cached[0] == current_team:
        return cached[1]

    include_children = request.COOKIES.get("include_children", "0") == "1"
    scope = _scope_for_user(request.user, current_team, include_children=include_children)
    setattr(request, _CACHE_ATTRIBUTE, (current_team, scope))
    return scope


def _permissions_from_scope(scope: WorkflowPermissionScope, workflow) -> list[str]:
    workflow_teams = _normalized_ids(getattr(workflow, "team", []))
    if not (workflow_teams & scope.organization_ids):
        return []
    if workflow_teams & scope.team_rule_ids:
        return list(DEFAULT_PERMISSION)
    return list(scope.instance_permissions.get(str(workflow.pk), []))


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
    return _permissions_from_scope(_scope(request, current_team), workflow)


def resolve_permission_actor(*, username: str, domain: str):
    """Resolve a permission actor for shared REST/OpenAPI instance checks."""

    user = get_user_model().objects.filter(username=username, domain=domain).first()
    if user is not None:
        return user
    return SimpleNamespace(username=username, domain=domain, is_superuser=False, group_tree=[])


def actor_can_access_workflow(
    *,
    username: str,
    domain: str,
    current_team: int,
    workflow,
    require_operate: bool = False,
    include_children: bool = False,
) -> bool:
    """Shared instance-scope gate used by REST-equivalent OpenAPI entrypoints."""

    user = resolve_permission_actor(username=username, domain=domain)
    if getattr(user, "is_superuser", False):
        workflow_teams = {int(item) for item in (getattr(workflow, "team", []) or []) if str(item).isdigit() or isinstance(item, int)}
        return int(current_team) in workflow_teams

    permissions = _permissions_from_scope(
        _scope_for_user(user, int(current_team), include_children=include_children),
        workflow,
    )
    needed = "Operate" if require_operate else "View"
    return needed in permissions or (not require_operate and "Operate" in permissions)


def actor_can_operate_workflow_for_teams(
    *,
    username: str,
    domain: str,
    team_ids,
    workflow,
) -> bool:
    """Fail closed: Operate must hold in at least one authorized overlapping team."""

    authorized = {int(item) for item in (team_ids or []) if isinstance(item, int) and not isinstance(item, bool)}
    workflow_teams = {int(item) for item in (getattr(workflow, "team", []) or []) if isinstance(item, int) and not isinstance(item, bool)}
    for team_id in authorized & workflow_teams:
        if actor_can_access_workflow(
            username=username,
            domain=domain,
            current_team=team_id,
            workflow=workflow,
            require_operate=True,
        ):
            return True
    return False
