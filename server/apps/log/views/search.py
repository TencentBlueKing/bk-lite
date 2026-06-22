import os

from rest_framework.decorators import action
from rest_framework.viewsets import ViewSet, ModelViewSet

from apps.core.utils.web_utils import WebUtils
from apps.log.services.search import SearchService
from apps.log.services.access_scope import LogAccessScopeService
from apps.log.models.log_group import SearchCondition
from apps.log.serializers.log_group import SearchConditionSerializer
from apps.log.serializers.search import LogFieldValuesSerializer, LogHitsSerializer, LogSearchSerializer, LogTopStatsSerializer
from apps.log.filters.log_group import SearchConditionFilter
from apps.core.utils.team_utils import get_current_team


class LogSearchViewSet(ViewSet):
    def _field_values_response(self, request):
        serializer = LogFieldValuesSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data
        query = request.query_params.get("query", "*")
        log_groups = request.query_params.getlist("log_groups") or request.query_params.getlist("log_groups[]")

        if not log_groups:
            return WebUtils.response_error(error_message="缺少日志分组", status_code=400)

        try:
            scope = LogAccessScopeService.resolve_scope(request, log_groups)
        except ValueError as exc:
            return WebUtils.response_error(error_message=str(exc), status_code=403)

        data = SearchService.field_values(
            validated_data.get("start_time", ""),
            validated_data.get("end_time", ""),
            validated_data["filed"],
            validated_data.get("limit", 100),
            query=query,
            log_groups=scope.log_groups,
            resolved_groups=scope.resolved_group_objects,
        )
        return WebUtils.response_success(data)

    @action(methods=["get"], detail=False, url_path="field_names")
    def field_names(self, request):
        """
        Backward-compatible alias for available log field values.
        """
        return self._field_values_response(request)

    @action(methods=["get"], detail=False, url_path="field_values")
    def field_values(self, request):
        """Search available log field values."""
        return self._field_values_response(request)

    @action(methods=["post"], detail=False, url_path="search")
    def search(self, request):
        """
        Search logs based on the provided query parameters.
        """
        serializer = LogSearchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data
        log_groups = validated_data.get("log_groups", [])

        try:
            scope = LogAccessScopeService.resolve_scope(request, log_groups)
        except ValueError as exc:
            return WebUtils.response_error(error_message=str(exc), status_code=403)

        data = SearchService.search_logs(
            validated_data["query"],
            validated_data.get("start_time", ""),
            validated_data.get("end_time", ""),
            validated_data.get("limit", 10),
            scope.log_groups,
            resolved_groups=scope.resolved_group_objects,
        )
        return WebUtils.response_success(data)

    @action(methods=["post"], detail=False, url_path="hits")
    def hits(self, request):
        """
        Search hits based on the provided query parameters.
        """
        serializer = LogHitsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data
        log_groups = validated_data.get("log_groups", [])

        try:
            scope = LogAccessScopeService.resolve_scope(request, log_groups)
        except ValueError as exc:
            return WebUtils.response_error(error_message=str(exc), status_code=403)

        data = SearchService.search_hits(
            validated_data["query"],
            validated_data.get("start_time", ""),
            validated_data.get("end_time", ""),
            validated_data["field"],
            validated_data.get("fields_limit", 5),
            validated_data.get("step", "5m"),
            scope.log_groups,
            resolved_groups=scope.resolved_group_objects,
        )
        return WebUtils.response_success(data)

    @action(methods=["post"], detail=False, url_path="top_stats")
    def top_stats(self, request):
        """按字段返回 TopN 统计结果。"""
        serializer = LogTopStatsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        validated_data = serializer.validated_data
        log_groups = validated_data.get("log_groups", [])

        try:
            scope = LogAccessScopeService.resolve_scope(request, log_groups)
        except ValueError as exc:
            return WebUtils.response_error(error_message=str(exc), status_code=403)

        data = SearchService.top_stats(
            query=validated_data.get("query", "*"),
            start_time=validated_data.get("start_time", ""),
            end_time=validated_data.get("end_time", ""),
            attr=validated_data["attr"],
            top_num=validated_data.get("top_num", 5),
            log_groups=scope.log_groups,
            resolved_groups=scope.resolved_group_objects,
        )
        return WebUtils.response_success(data)

    @action(methods=["get"], detail=False, url_path="tail")
    def tail_logs(self, request):
        """
        实现长连接接口，用于实时获取日志数据
        """
        query = request.query_params.get("query", "")
        log_groups_param = request.query_params.get("log_groups", "")

        # 解析log_groups参数
        log_groups = []
        if log_groups_param:
            log_groups = [group.strip() for group in log_groups_param.split(",") if group.strip()]

        if not query:
            return WebUtils.response_error("Query parameters are required.")
        if not log_groups:
            return WebUtils.response_error(error_message="缺少日志分组", status_code=400)

        try:
            scope = LogAccessScopeService.resolve_scope(request, log_groups)
        except ValueError as exc:
            return WebUtils.response_error(error_message=str(exc), status_code=403)

        return SearchService.tail(query, scope.log_groups, resolved_groups=scope.resolved_group_objects)


class SearchConditionViewSet(ModelViewSet):
    """搜索条件管理ViewSet"""

    queryset = SearchCondition.objects.all()
    serializer_class = SearchConditionSerializer
    filterset_class = SearchConditionFilter

    def _get_accessible_group_ids(self):
        try:
            queryset, _ = LogAccessScopeService.get_accessible_group_queryset(self.request)
            return set(queryset.values_list("id", flat=True))
        except ValueError:
            return set()

    def _is_accessible_search_condition(self, instance, accessible_group_ids):
        condition = instance.condition if isinstance(instance.condition, dict) else {}
        log_groups = condition.get("log_groups", [])
        if not isinstance(log_groups, list):
            return False

        if not log_groups:
            return bool(accessible_group_ids)

        return all(str(gid).strip() in accessible_group_ids for gid in log_groups if str(gid).strip())

    def get_queryset(self):
        """根据当前组织过滤查询集"""
        current_team = get_current_team(self.request)
        if not current_team:
            return SearchCondition.objects.none()

        org_id = int(current_team)
        accessible_group_ids = self._get_accessible_group_ids()

        # 仅拉取权限过滤所需的两列（id + condition），并流式迭代避免全量驻内存。
        # 这样 N 条记录只产生 N 个轻量 dict，而非 N 个完整 ORM 对象。
        slim_qs = (
            SearchCondition.objects.filter(organization=org_id)
            .only("id", "condition")
            .iterator(chunk_size=int(os.getenv("SEARCH_CONDITION_CHUNK_SIZE", "200")))
        )
        accessible_ids = [
            row.id
            for row in slim_qs
            if self._is_accessible_search_condition(row, accessible_group_ids)
        ]
        if not accessible_ids:
            return SearchCondition.objects.none()
        return SearchCondition.objects.filter(organization=org_id, id__in=accessible_ids)

    def create(self, request, *args, **kwargs):
        """创建搜索条件"""
        current_team = get_current_team(request)
        if not current_team:
            return WebUtils.response_error("当前组织信息不存在，请重新登录")

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # 设置创建者和组织
        serializer.validated_data["created_by"] = request.user.username
        serializer.validated_data["organization"] = int(current_team)

        search_condition = serializer.save()

        return WebUtils.response_success(
            {
                "id": search_condition.id,
                "name": search_condition.name,
                "message": "搜索条件创建成功",
            }
        )

    def list(self, request, *args, **kwargs):
        """获取搜索条件列表"""
        current_team = get_current_team(request)
        if not current_team:
            return WebUtils.response_error("当前组织信息不存在，请重新登录")

        queryset = self.filter_queryset(self.get_queryset())

        # 分页处理
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return WebUtils.response_success(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        """获取搜索条件详情"""
        current_team = get_current_team(request)
        if not current_team:
            return WebUtils.response_error("当前组织信息不存在，请重新登录")

        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return WebUtils.response_success(serializer.data)

    def update(self, request, *args, **kwargs):
        """更新搜索条件"""
        current_team = get_current_team(request)
        if not current_team:
            return WebUtils.response_error("当前组织信息不存在，请重新登录")

        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        # 设置更新者（不允许修改组织）
        serializer.validated_data["updated_by"] = request.user.username

        search_condition = serializer.save()

        return WebUtils.response_success(
            {
                "id": search_condition.id,
                "name": search_condition.name,
                "message": "搜索条件更新成功",
            }
        )

    def partial_update(self, request, *args, **kwargs):
        """部分更新搜索条件"""
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        """删除搜索条件"""
        current_team = get_current_team(request)
        if not current_team:
            return WebUtils.response_error("当前组织信息不存在，请重新登录")

        instance = self.get_object()
        search_condition_name = instance.name
        instance.delete()

        return WebUtils.response_success({"message": f"搜索条件 '{search_condition_name}' 删除成功"})
