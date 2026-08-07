"""补丁管理的主机根数据权限。

PatchTarget 是补丁管理唯一的数据权限根。风险、执行记录、看板和
基线绑定主机均应通过本模块投影，不得再叠加补丁、基线或任务的
实例数据权限。
"""

from __future__ import annotations

from dataclasses import dataclass

from django.db.models import Q, QuerySet
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.core.logger import logger
from apps.core.utils import viewset_utils
from apps.core.utils.team_utils import get_current_team
from apps.core.utils.viewset_utils import build_json_membership_query
from apps.patch_mgmt.models import PatchTarget
from apps.patch_mgmt.utils.i18n import patch_message


@dataclass(frozen=True)
class _TargetRules:
    team_ids: tuple[int, ...]
    visible_instance_ids: tuple[int, ...]
    operable_instance_ids: tuple[int, ...]


class TargetAccessScope:
    """一次请求内的主机可见/可操作范围。"""

    permission_key = "patch_target"

    def __init__(self, request):
        self.request = request
        self.user = getattr(request, "user", None)
        self.current_team = self._validate_current_team()
        self.include_children = request.COOKIES.get("include_children", "0") == "1"
        self._rules = self._load_rules()

    def _validate_current_team(self) -> int:
        if self.user is None:
            raise PermissionDenied("用户未登录")
        try:
            current_team = int(get_current_team(self.request, "0"))
        except (TypeError, ValueError) as exc:
            raise PermissionDenied("无权访问该组织数据") from exc
        if current_team <= 0:
            raise PermissionDenied("无权访问该组织数据")
        if getattr(self.user, "is_superuser", False):
            return current_team
        group_ids = {
            int(item["id"])
            for item in (getattr(self.user, "group_list", []) or [])
            if isinstance(item, dict) and str(item.get("id", "")).isdigit()
        }
        if current_team not in group_ids:
            raise PermissionDenied("无权访问该组织数据")
        return current_team

    def _load_rules(self) -> _TargetRules:
        if getattr(self.user, "is_superuser", False):
            return _TargetRules((), (), ())
        try:
            payload = viewset_utils.get_permission_rules(
                self.user,
                self.current_team,
                "patch_mgmt",
                self.permission_key,
                self.include_children,
            )
        except Exception:  # noqa: BLE001 - 权限边界故障必须 fail closed
            logger.exception("获取补丁目标数据权限失败")
            payload = {}

        team_ids = tuple(
            int(value)
            for value in (payload.get("team", []) or [])
            if str(value).isdigit()
        )
        visible: set[int] = set()
        operable: set[int] = set()
        for item in payload.get("instance", []) or []:
            try:
                instance_id = int(item["id"])
            except (KeyError, TypeError, ValueError):
                continue
            permissions = set(item.get("permission") or [])
            if permissions.intersection({"View", "Operate"}):
                visible.add(instance_id)
            if "Operate" in permissions:
                operable.add(instance_id)
        return _TargetRules(team_ids, tuple(visible), tuple(operable))

    def queryset(self, operation: str = "View") -> QuerySet:
        queryset = PatchTarget.objects.all()
        if getattr(self.user, "is_superuser", False):
            return queryset
        instance_ids = (
            self._rules.operable_instance_ids
            if operation == "Operate"
            else self._rules.visible_instance_ids
        )
        team_query = build_json_membership_query(
            queryset, "team", self._rules.team_ids
        )
        return queryset.filter(team_query | Q(pk__in=instance_ids))

    def filter(self, queryset: QuerySet, operation: str = "View") -> QuerySet:
        return queryset.filter(pk__in=self.queryset(operation).values("pk"))

    def require(self, ids, operation: str = "Operate") -> set[int]:
        try:
            requested = {int(value) for value in ids if value is not None}
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                patch_message(
                    self.request,
                    "error.data_id_integer",
                    "Data ID must be an integer",
                )
            ) from exc
        authorized = set(
            self.queryset(operation)
            .filter(pk__in=requested)
            .values_list("pk", flat=True)
        )
        denied = sorted(requested - authorized)
        if denied:
            raise PermissionDenied(
                patch_message(
                    self.request,
                    "error.data_access_denied",
                    "You do not have access to the selected data: {ids}",
                    ids=denied,
                )
            )
        return requested


def target_access_scope(request) -> TargetAccessScope:
    """请求级缓存，避免同一 API 重复请求数据权限服务。"""
    cached = getattr(request, "_patch_target_access_scope", None)
    if cached is None:
        cached = TargetAccessScope(request)
        request._patch_target_access_scope = cached
    return cached


def require_target_ids(request, ids, operation: str = "Operate") -> set[int]:
    return target_access_scope(request).require(ids, operation)


class GlobalSharedResourceMixin:
    """共享资源只受功能权限控制，team 仅作来源/审计字段。"""

    def create(self, request, *args, **kwargs):
        self._validate_current_team_permission(request)
        return super().create(request, *args, **kwargs)

    def get_object(self):
        self._validate_current_team_permission(self.request)
        return super().get_object()

    def get_queryset_by_permission(self, request, queryset, permission_key=None):
        del permission_key
        self._validate_current_team_permission(request)
        return queryset

    def get_detail(self, request, *args, **kwargs):
        self._validate_current_team_permission(request)
        return self.get_serializer(self.get_object())

    def _validate_update_access(self, request, instance, data):
        del instance
        self._validate_current_team_permission(request)
        org_field = self.ORGANIZATION_FIELD
        if org_field in data:
            self._validate_org_field_permission(
                request,
                self._normalize_org_values(data, org_field),
            )
        return None

    def _validate_destroy_access(self, request, instance):
        del instance
        self._validate_current_team_permission(request)
        return None

    def delete_rules(self, instance_id, delete_team):
        # 旧的非目标数据权限规则保留但不再生效，不因 team 变更清理。
        del instance_id, delete_team


class TargetRootedResourceMixin:
    """PatchTarget 自身列表与对象操作使用同一权限语义。"""

    def get_queryset_by_permission(self, request, queryset, permission_key=None):
        if (permission_key or getattr(self, "permission_key", None)) == "patch_target":
            return target_access_scope(request).filter(queryset, "View")
        return super().get_queryset_by_permission(
            request, queryset, permission_key=permission_key
        )

    def get_detail(self, request, *args, **kwargs):
        instance = self.get_object()
        require_target_ids(request, [instance.id], "View")
        return self.get_serializer(instance)

    def _validate_update_access(self, request, instance, data):
        del data
        require_target_ids(request, [instance.id], "Operate")
        return None

    def _validate_destroy_access(self, request, instance):
        require_target_ids(request, [instance.id], "Operate")
        return None
