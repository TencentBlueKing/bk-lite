from rest_framework import viewsets

from apps.core.utils.permission_utils import get_permission_rules, permission_filter
from apps.core.utils.web_utils import WebUtils
from apps.monitor.constants.database import DatabaseConstants
from apps.monitor.constants.permission import PermissionConstants
from apps.monitor.filters.monitor_condition import MonitorConditionFilter
from apps.monitor.models.monitor_condition import (
    MonitorCondition,
    MonitorConditionOrganization,
)
from apps.monitor.serializers.monitor_condition import MonitorConditionSerializer
from apps.monitor.utils.pagination import parse_page_params
from config.drf.pagination import CustomPageNumberPagination


class MonitorConditionViewSet(viewsets.ModelViewSet):
    queryset = MonitorCondition.objects.all()
    serializer_class = MonitorConditionSerializer
    filterset_class = MonitorConditionFilter
    pagination_class = CustomPageNumberPagination

    def list(self, request, *args, **kwargs):
        monitor_object_id = request.query_params.get("monitor_object_id", None)

        include_children = request.COOKIES.get("include_children", "0") == "1"
        permission = get_permission_rules(
            request.user,
            request.COOKIES.get("current_team"),
            "monitor",
            f"{PermissionConstants.CONDITION_MODULE}.{monitor_object_id}",
            include_children=include_children,
        )
        qs = permission_filter(
            MonitorCondition,
            permission,
            team_key="organizations__organization__in",
            id_key="id__in",
        )

        queryset = self.filter_queryset(qs)
        queryset = queryset.distinct()

        # 获取分页参数
        page, page_size = parse_page_params(
            request.GET, default_page=1, default_page_size=10
        )

        # 计算分页的起始位置
        start = (page - 1) * page_size
        end = start + page_size

        # 获取当前页的数据
        page_data = queryset[start:end]

        # 执行序列化
        serializer = self.get_serializer(page_data, many=True)
        results = serializer.data

        # 如果有权限规则，则添加到数据中
        inst_permission_map = {
            i["id"]: i["permission"] for i in permission.get("instance", [])
        }

        for instance_info in results:
            if instance_info["id"] in inst_permission_map:
                instance_info["permission"] = inst_permission_map[instance_info["id"]]
            else:
                instance_info["permission"] = PermissionConstants.DEFAULT_PERMISSION

        return WebUtils.response_success(dict(count=queryset.count(), items=results))

    def create(self, request, *args, **kwargs):
        request.data["created_by"] = request.user.username
        response = super().create(request, *args, **kwargs)
        condition_id = response.data["id"]
        organizations = request.data.get("organizations", [])
        self.update_condition_organizations(condition_id, organizations)
        return response

    def update(self, request, *args, **kwargs):
        request.data["updated_by"] = request.user.username
        condition_id = kwargs["pk"]
        response = super().update(request, *args, **kwargs)
        organizations = request.data.get("organizations", [])
        if organizations:
            self.update_condition_organizations(condition_id, organizations)
        return response

    def partial_update(self, request, *args, **kwargs):
        request.data["updated_by"] = request.user.username
        condition_id = kwargs["pk"]
        response = super().partial_update(request, *args, **kwargs)
        organizations = request.data.get("organizations", [])
        if organizations:
            self.update_condition_organizations(condition_id, organizations)
        return response

    def destroy(self, request, *args, **kwargs):
        condition_id = kwargs["pk"]
        MonitorConditionOrganization.objects.filter(
            monitor_condition_id=condition_id
        ).delete()
        return super().destroy(request, *args, **kwargs)

    def update_condition_organizations(self, condition_id, organizations):
        """更新条件的组织"""
        old_organizations = MonitorConditionOrganization.objects.filter(
            monitor_condition_id=condition_id
        )
        old_set = set([org.organization for org in old_organizations])
        new_set = set(organizations)
        # 删除不存在的组织
        delete_set = old_set - new_set
        MonitorConditionOrganization.objects.filter(
            monitor_condition_id=condition_id, organization__in=delete_set
        ).delete()
        # 添加新的组织
        create_set = new_set - old_set
        create_objs = [
            MonitorConditionOrganization(
                monitor_condition_id=condition_id, organization=org_id
            )
            for org_id in create_set
        ]
        MonitorConditionOrganization.objects.bulk_create(
            create_objs, batch_size=DatabaseConstants.BULK_CREATE_BATCH_SIZE
        )
