from rest_framework.viewsets import ModelViewSet
from apps.core.utils.web_utils import WebUtils
from apps.core.utils.permission_utils import get_permission_rules, permission_filter
from apps.log.models.log_group import LogGroup, LogGroupOrganization
from apps.log.serializers.log_group import LogGroupSerializer
from apps.log.filters.log_group import LogGroupFilter
from apps.log.constants.permission import PermissionConstants


class LogGroupViewSet(ModelViewSet):
    queryset = LogGroup.objects.all()
    serializer_class = LogGroupSerializer
    filterset_class = LogGroupFilter

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # 设置创建者
        serializer.validated_data['created_by'] = request.user.username

        log_group = serializer.save()

        return WebUtils.response_success({
            "id": log_group.id,
            "name": log_group.name
        })

    def list(self, request, *args, **kwargs):
        # 获取权限规则
        permission = get_permission_rules(
            request.user,
            request.COOKIES.get("current_team"),
            "log",
            PermissionConstants.LOG_GROUP_MODULE,
        )

        # 应用权限过滤
        queryset = permission_filter(
            LogGroup,
            permission,
            team_key="loggrouporganization__organization__in",
            id_key="id__in"
        )

        # 应用过滤器
        queryset = self.filter_queryset(queryset)

        # 检查是否为全量查询（page_size为-1时不分页）
        page_size = request.query_params.get('page_size')
        if page_size == '-1':
            # 全量查询，直接返回所有数据
            serializer = self.get_serializer(queryset, many=True)
            return WebUtils.response_success(serializer.data)

        # 分页
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return WebUtils.response_success(serializer.data)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        # 设置更新者
        serializer.validated_data['updated_by'] = request.user.username

        log_group = serializer.save()

        return WebUtils.response_success({
            "id": log_group.id,
            "name": log_group.name
        })

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        log_group_name = instance.name

        # 删除相关的组织关联
        LogGroupOrganization.objects.filter(log_group=instance).delete()

        # 删除日志分组
        instance.delete()

        return WebUtils.response_success({
            "name": log_group_name
        })
