from rest_framework.decorators import action
from rest_framework.viewsets import ViewSet, ModelViewSet

from apps.core.utils.web_utils import WebUtils
from apps.log.services.search import SearchService
from apps.log.utils.log_group import LogGroupQueryBuilder
from apps.log.models.log_group import SearchCondition
from apps.log.serializers.log_group import SearchConditionSerializer
from apps.log.filters.log_group import SearchConditionFilter


class LogSearchViewSet(ViewSet):

    @action(methods=['get'], detail=False, url_path='field_names')
    def field_names(self, request):
        """
        Search available log field_names.
        """
        field = request.query_params.get('filed', '')
        start_time = request.query_params.get('start_time', '')
        end_time = request.query_params.get('end_time', '')
        limit = int(request.query_params.get('limit', 100))

        if not field:
            return WebUtils.response_error("Field parameter is required.")

        data = SearchService.field_names(start_time, end_time, field, limit)
        return WebUtils.response_success(data)

    @action(methods=['post'], detail=False, url_path='search')
    def search(self, request):
        """
        Search logs based on the provided query parameters.
        """
        query = request.data.get('query', '')
        start_time = request.data.get('start_time', '')
        end_time = request.data.get('end_time', '')
        limit = request.data.get('limit', 10)
        log_groups = request.data.get('log_groups', [])

        if not query:
            return WebUtils.response_error("Query parameter is required.")

        # 验证日志分组
        is_valid, error_msg, _ = LogGroupQueryBuilder.validate_log_groups(log_groups)
        if not is_valid:
            return WebUtils.response_error(error_msg)

        data = SearchService.search_logs(query, start_time, end_time, limit, log_groups)
        return WebUtils.response_success(data)

    @action(methods=['post'], detail=False, url_path='hits')
    def hits(self, request):
        """
        Search hits based on the provided query parameters.
        """
        query = request.data.get('query', '')
        start_time = request.data.get('start_time', '')
        end_time = request.data.get('end_time', '')
        field = request.data.get('field', '')
        fields_limit = request.data.get('fields_limit', 5)
        step = request.data.get('step', '5m')
        log_groups = request.data.get('log_groups', [])

        if not query or not field:
            return WebUtils.response_error("Query and field parameters are required.")

        # 验证日志分组
        is_valid, error_msg, _ = LogGroupQueryBuilder.validate_log_groups(log_groups)
        if not is_valid:
            return WebUtils.response_error(error_msg)

        data = SearchService.search_hits(query, start_time, end_time, field, fields_limit, step, log_groups)
        return WebUtils.response_success(data)

    @action(methods=['get'], detail=False, url_path='tail')
    def tail_logs(self, request):
        """
        实现长连接接口，用于实时获取日志数据
        """
        query = request.query_params.get("query", "")
        log_groups_param = request.query_params.get("log_groups", "")

        # 解析log_groups参数
        log_groups = []
        if log_groups_param:
            log_groups = [group.strip() for group in log_groups_param.split(',') if group.strip()]

        if not log_groups:
            return WebUtils.response_error("log_groups parameter is required.")

        if not query:
            return WebUtils.response_error("Query parameters are required.")

        # 验证日志分组
        is_valid, error_msg, _ = LogGroupQueryBuilder.validate_log_groups(log_groups)
        if not is_valid:
            return WebUtils.response_error(error_msg)

        return SearchService.tail(query, log_groups)

class SearchConditionViewSet(ModelViewSet):
    """搜索条件管理ViewSet"""
    queryset = SearchCondition.objects.all()
    serializer_class = SearchConditionSerializer
    filterset_class = SearchConditionFilter

    def get_queryset(self):
        """根据当前组织过滤查询集"""
        current_team = self.request.COOKIES.get("current_team")
        if current_team:
            return SearchCondition.objects.filter(organization=int(current_team))
        return SearchCondition.objects.none()

    def create(self, request, *args, **kwargs):
        """创建搜索条件"""
        current_team = request.COOKIES.get("current_team")
        if not current_team:
            return WebUtils.response_error("当前组织信息不存在，请重新登录")

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # 设置创建者和组织
        serializer.validated_data['created_by'] = request.user.username
        serializer.validated_data['organization'] = int(current_team)

        search_condition = serializer.save()

        return WebUtils.response_success({
            "id": search_condition.id,
            "name": search_condition.name,
            "message": "搜索条件创建成功"
        })

    def list(self, request, *args, **kwargs):
        """获取搜索条件列表"""
        current_team = request.COOKIES.get("current_team")
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
        current_team = request.COOKIES.get("current_team")
        if not current_team:
            return WebUtils.response_error("当前组织信息不存在，请重新登录")

        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return WebUtils.response_success(serializer.data)

    def update(self, request, *args, **kwargs):
        """更新搜索条件"""
        current_team = request.COOKIES.get("current_team")
        if not current_team:
            return WebUtils.response_error("当前组织信息不存在，请重新登录")

        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        # 设置更新者（不允许修改组织）
        serializer.validated_data['updated_by'] = request.user.username

        search_condition = serializer.save()

        return WebUtils.response_success({
            "id": search_condition.id,
            "name": search_condition.name,
            "message": "搜索条件更新成功"
        })

    def partial_update(self, request, *args, **kwargs):
        """部分更新搜索条件"""
        kwargs['partial'] = True
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        """删除搜索条件"""
        current_team = request.COOKIES.get("current_team")
        if not current_team:
            return WebUtils.response_error("当前组织信息不存在，请重新登录")

        instance = self.get_object()
        search_condition_name = instance.name
        instance.delete()

        return WebUtils.response_success({
            "message": f"搜索条件 '{search_condition_name}' 删除成功"
        })
