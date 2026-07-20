from rest_framework import status, viewsets
from rest_framework.response import Response

from apps.core.utils.current_team_scope import resolve_current_team_data_scope, scope_permission_queryset, validate_assignable_organizations
from apps.core.utils.permission_utils import get_permission_rules
from apps.core.utils.team_utils import get_current_team
from apps.core.utils.web_utils import WebUtils
from apps.monitor.constants.database import DatabaseConstants
from apps.monitor.constants.permission import PermissionConstants
from apps.monitor.filters.monitor_condition import MonitorConditionFilter
from apps.monitor.models.monitor_condition import MonitorCondition, MonitorConditionOrganization
from apps.monitor.serializers.monitor_condition import MonitorConditionSerializer
from apps.monitor.utils.pagination import parse_page_params
from config.drf.pagination import CustomPageNumberPagination


def _operate_only_permission(permission):
    return {
        **permission,
        "team": permission.get("team", []),
        "instance": [item for item in permission.get("instance", []) if isinstance(item, dict) and "Operate" in item.get("permission", [])],
    }


class MonitorConditionViewSet(viewsets.ModelViewSet):
    queryset = MonitorCondition.objects.all()
    serializer_class = MonitorConditionSerializer
    filterset_class = MonitorConditionFilter
    pagination_class = CustomPageNumberPagination

    def _get_permission(self):
        return get_permission_rules(
            self.request.user,
            get_current_team(self.request),
            "monitor",
            PermissionConstants.CONDITION_MODULE,
            include_children=self.request.COOKIES.get("include_children", "0") == "1",
        )

    def _get_data_scope(self):
        if not hasattr(self, "_current_team_data_scope"):
            self._current_team_data_scope = resolve_current_team_data_scope(self.request)
        return self._current_team_data_scope

    def _get_effective_permission(self):
        scope = self._get_data_scope()
        if self.request.user.is_superuser:
            return {"team": list(scope.data_team_ids), "instance": []}
        return self._get_permission()

    def _scope_queryset(self, queryset, permission, scope):
        permitted_qs = scope_permission_queryset(
            MonitorCondition,
            permission,
            scope,
            team_key="organizations__organization__in",
            id_key="id__in",
        )
        return queryset.filter(id__in=permitted_qs.values("id")).distinct()

    def get_queryset(self):
        queryset = super().get_queryset()
        request = getattr(self, "request", None)
        if request is None:
            return queryset

        scope = self._get_data_scope()
        permission = self._get_effective_permission()
        if not request.user.is_superuser and getattr(self, "action", "") in {"update", "partial_update", "destroy"}:
            permission = _operate_only_permission(permission)
        return self._scope_queryset(queryset, permission, scope)

    def _ensure_target_organizations(self, organizations, actor_context=None):
        if not organizations:
            return
        validate_assignable_organizations(self.request, organizations)

    def list(self, request, *args, **kwargs):
        permission = self._get_effective_permission()
        queryset = self.filter_queryset(self.get_queryset())
        queryset = queryset.distinct()

        page, page_size = parse_page_params(request.GET, default_page=1, default_page_size=10)

        start = (page - 1) * page_size
        end = start + page_size

        page_data = queryset[start:end]

        serializer = self.get_serializer(page_data, many=True)
        results = serializer.data

        inst_permission_map = {i["id"]: i["permission"] for i in permission.get("instance", [])}

        for instance_info in results:
            if instance_info["id"] in inst_permission_map:
                instance_info["permission"] = inst_permission_map[instance_info["id"]]
            else:
                instance_info["permission"] = PermissionConstants.DEFAULT_PERMISSION

        return WebUtils.response_success(dict(count=queryset.count(), items=results))

    def create(self, request, *args, **kwargs):
        self._ensure_target_organizations(request.data.get("organizations", []))
        request.data["created_by"] = request.user.username
        response = super().create(request, *args, **kwargs)
        condition_id = response.data["id"]
        organizations = request.data.get("organizations", [])
        self.update_condition_organizations(condition_id, organizations)
        return response

    def update(self, request, *args, **kwargs):
        condition = self.get_object()
        self._ensure_target_organizations(request.data.get("organizations", []))
        request.data["updated_by"] = request.user.username
        condition_id = condition.id
        response = super().update(request, *args, **kwargs)
        organizations = request.data.get("organizations", [])
        if organizations:
            self.update_condition_organizations(condition_id, organizations)
        return response

    def partial_update(self, request, *args, **kwargs):
        condition = self.get_object()
        if "organizations" in request.data:
            self._ensure_target_organizations(request.data.get("organizations", []))
        request.data["updated_by"] = request.user.username
        condition_id = condition.id
        response = super().partial_update(request, *args, **kwargs)
        organizations = request.data.get("organizations", [])
        if organizations:
            self.update_condition_organizations(condition_id, organizations)
        return response

    def destroy(self, request, *args, **kwargs):
        condition = self.get_object()
        condition_id = condition.id
        MonitorConditionOrganization.objects.filter(monitor_condition_id=condition_id).delete()
        condition.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def update_condition_organizations(self, condition_id, organizations):
        """更新条件的组织"""
        old_organizations = MonitorConditionOrganization.objects.filter(monitor_condition_id=condition_id)
        old_set = set([org.organization for org in old_organizations])
        new_set = set(organizations)
        # 删除不存在的组织
        delete_set = old_set - new_set
        MonitorConditionOrganization.objects.filter(monitor_condition_id=condition_id, organization__in=delete_set).delete()
        # 添加新的组织
        create_set = new_set - old_set
        create_objs = [MonitorConditionOrganization(monitor_condition_id=condition_id, organization=org_id) for org_id in create_set]
        MonitorConditionOrganization.objects.bulk_create(create_objs, batch_size=DatabaseConstants.BULK_CREATE_BATCH_SIZE)
