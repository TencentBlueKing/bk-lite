from __future__ import annotations

from dataclasses import dataclass

from apps.core.utils.permission_utils import get_permission_rules, permission_filter
from apps.log.constants.permission import PermissionConstants
from apps.log.models.log_group import LogGroup
from apps.core.utils.team_utils import get_current_team


@dataclass
class LogAccessScope:
    log_groups: list[str]
    queryset: object
    permission: dict
    resolved_group_objects: list = None

    def __post_init__(self):
        if self.resolved_group_objects is None:
            self.resolved_group_objects = []


class LogAccessScopeService:
    @staticmethod
    def _get_current_team(request):
        current_team = get_current_team(request)
        if current_team in (None, ""):
            raise ValueError("当前组织信息不存在，请重新登录")
        return current_team

    @staticmethod
    def _normalize_team_ids(values):
        normalized = set()
        for item in values or []:
            if isinstance(item, dict):
                item = item.get("id")
            try:
                normalized.add(int(item))
            except (TypeError, ValueError):
                continue
        return normalized

    @classmethod
    def get_group_permission(cls, request):
        current_team = cls._get_current_team(request)
        include_children = request.COOKIES.get("include_children", "0") == "1"
        permission = get_permission_rules(
            request.user,
            current_team,
            "log",
            PermissionConstants.LOG_GROUP_MODULE,
            include_children=include_children,
        )
        return permission if isinstance(permission, dict) else {}

    @classmethod
    def get_accessible_group_queryset(cls, request):
        permission = cls.get_group_permission(request)
        queryset = permission_filter(
            LogGroup,
            permission,
            team_key="loggrouporganization__organization__in",
            id_key="id__in",
        ).distinct()
        return queryset, permission

    @classmethod
    def get_manageable_organization_ids(cls, request):
        _, permission = cls.get_accessible_group_queryset(request)
        return cls._normalize_team_ids(permission.get("team", []))

    @classmethod
    def validate_organizations(cls, request, organizations):
        if organizations in (None, []):
            return

        allowed_organizations = cls.get_manageable_organization_ids(request)
        unauthorized = sorted(set(organizations) - allowed_organizations)
        if unauthorized:
            raise ValueError(f"以下组织无权限绑定日志分组: {', '.join(str(org) for org in unauthorized)}")

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
        )
