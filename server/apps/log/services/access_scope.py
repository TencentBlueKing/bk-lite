from __future__ import annotations

from dataclasses import dataclass

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.utils.current_team_scope import resolve_current_team_data_scope, scope_permission_queryset, validate_assignable_organizations
from apps.core.utils.permission_utils import get_permission_rules
from apps.log.constants.permission import PermissionConstants
from apps.log.models.log_group import LogGroup


@dataclass
class LogAccessScope:
    log_groups: list[str]
    queryset: object
    permission: dict
    resolved_group_objects: list = None
    data_team_ids: frozenset[int] = frozenset()

    def __post_init__(self):
        if self.resolved_group_objects is None:
            self.resolved_group_objects = []


class LogAccessScopeService:
    @classmethod
    def get_data_scope(cls, request):
        cache_key = "_log_current_team_data_scope"
        scope = getattr(request, cache_key, None)
        if scope is not None:
            return scope
        try:
            scope = resolve_current_team_data_scope(request)
        except BaseAppException as exc:
            raise ValueError(str(exc)) from exc
        setattr(request, cache_key, scope)
        return scope

    @classmethod
    def get_group_permission(cls, request, scope=None):
        scope = scope or cls.get_data_scope(request)
        if scope.is_superuser:
            return {"team": list(scope.data_team_ids), "instance": []}
        permission = get_permission_rules(
            request.user,
            scope.current_team,
            "log",
            PermissionConstants.LOG_GROUP_MODULE,
            include_children=scope.include_children,
        )
        return permission if isinstance(permission, dict) else {}

    @classmethod
    def get_accessible_group_queryset(cls, request):
        scope = cls.get_data_scope(request)
        permission = cls.get_group_permission(request, scope)
        queryset = scope_permission_queryset(
            LogGroup,
            permission,
            scope,
            team_key="loggrouporganization__organization__in",
            id_key="id__in",
        )
        return queryset, permission

    @classmethod
    def get_manageable_organization_ids(cls, request):
        return set(cls.get_data_scope(request).data_team_ids)

    @classmethod
    def validate_organizations(cls, request, organizations):
        try:
            return validate_assignable_organizations(request, organizations)
        except BaseAppException as exc:
            raise ValueError(str(exc)) from exc

    @classmethod
    def resolve_scope(cls, request, log_group_ids=None):
        if log_group_ids is None:
            log_group_ids = []

        if not isinstance(log_group_ids, list):
            raise ValueError("log_groups 必须是一个数组")

        requested_ids = []
        for group_id in log_group_ids:
            normalized = str(group_id).strip()
            if not normalized:
                continue
            requested_ids.append(normalized)

        queryset, permission = cls.get_accessible_group_queryset(request)

        if requested_ids:
            # 精确查询：只检查请求的分组是否在权限范围内
            accessible_requested = list(queryset.filter(id__in=requested_ids).only("id", "name", "rule"))
            accessible_map = {group.id: group for group in accessible_requested}

            unauthorized = sorted(set(requested_ids) - set(accessible_map.keys()))
            if unauthorized:
                raise ValueError(f"以下日志分组无权限访问或不存在: {', '.join(unauthorized)}")

            resolved_ids = []
            resolved_groups = []
            seen = set()
            for group_id in requested_ids:
                if group_id in accessible_map and group_id not in seen:
                    resolved_ids.append(group_id)
                    resolved_groups.append(accessible_map[group_id])
                    seen.add(group_id)
        else:
            # 空请求：返回所有可见分组（保持原有语义）
            accessible_groups = list(queryset.only("id", "name", "rule"))
            resolved_ids = [group.id for group in accessible_groups]
            resolved_groups = accessible_groups

        if not resolved_ids:
            raise ValueError("当前组织暂无可用的日志分组权限")

        return LogAccessScope(
            log_groups=resolved_ids,
            queryset=queryset.filter(id__in=resolved_ids),
            permission=permission,
            resolved_group_objects=resolved_groups,
            data_team_ids=cls.get_data_scope(request).data_team_ids,
        )
