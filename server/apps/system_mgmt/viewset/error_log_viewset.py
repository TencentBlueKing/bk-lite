from django.http import JsonResponse
from django_filters import rest_framework as filters
from rest_framework import permissions

from apps.core.utils.viewset_utils import LanguageViewSet
from apps.system_mgmt.models import ErrorLog
from apps.system_mgmt.serializers.error_log_serializer import ErrorLogSerializer
from apps.system_mgmt.utils.group_filter_mixin import GroupFilterMixin


class ErrorLogFilter(filters.FilterSet):
    """错误日志过滤器"""

    # 时间范围筛选
    time_start = filters.DateTimeFilter(field_name="created_at", lookup_expr="gte")
    time_end = filters.DateTimeFilter(field_name="created_at", lookup_expr="lte")

    # 用户名筛选（模糊）
    username = filters.CharFilter(field_name="username", lookup_expr="icontains")

    # 应用筛选（多选）
    app = filters.CharFilter(method="filter_app_in")

    # 模块筛选（模糊）
    module = filters.CharFilter(field_name="module", lookup_expr="icontains")

    class Meta:
        model = ErrorLog
        fields = ["time_start", "time_end", "username", "app", "module"]

    def filter_app_in(self, queryset, name, value):
        """应用多选筛选"""
        if not value:
            return queryset
        # 支持逗号分隔的多个应用
        app_list = [app.strip() for app in value.split(",") if app.strip()]
        if app_list:
            return queryset.filter(app__in=app_list)
        return queryset


class ErrorLogViewSet(GroupFilterMixin, LanguageViewSet):
    """
    错误日志视图集

    功能说明：
    1. 支持时间范围查询（time_start, time_end）
    2. 多维度筛选（用户、应用、模块）
    3. 自动分页，按时间倒序
    4. 只读接口，不支持创建、修改、删除

    继承GroupFilterMixin实现基于current_team的组过滤
    """

    queryset = ErrorLog.objects.all().order_by("-created_at")
    serializer_class = ErrorLogSerializer
    filterset_class = ErrorLogFilter
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "head", "options"]

    def retrieve(self, request, *args, **kwargs):
        """禁用详情接口"""
        message = self.loader.get("error.detail_not_supported") if self.loader else "不支持详情查询"
        return JsonResponse({"result": False, "message": message}, status=405)

    def create(self, request, *args, **kwargs):
        """禁用创建接口"""
        message = self.loader.get("error.create_not_supported") if self.loader else "不支持手动创建"
        return JsonResponse({"result": False, "message": message}, status=405)

    def update(self, request, *args, **kwargs):
        """禁用更新接口"""
        message = self.loader.get("error.update_not_supported") if self.loader else "不支持修改"
        return JsonResponse({"result": False, "message": message}, status=405)

    def destroy(self, request, *args, **kwargs):
        """禁用删除接口"""
        message = self.loader.get("error.delete_not_supported") if self.loader else "不支持删除"
        return JsonResponse({"result": False, "message": message}, status=405)
