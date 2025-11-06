from django_filters import rest_framework as filters
from rest_framework import permissions
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.utils.viewset_utils import LanguageViewSet
from apps.system_mgmt.models import UserLoginLog
from apps.system_mgmt.serializers.user_login_log_serializer import UserLoginLogSerializer


class UserLoginLogFilter(filters.FilterSet):
    """用户登录日志过滤器"""

    # 登录状态筛选：success/failed
    status = filters.CharFilter(field_name="status", lookup_expr="exact")

    # 用户名筛选：支持精确匹配和模糊匹配
    username = filters.CharFilter(field_name="username", lookup_expr="icontains")

    # 登录时间范围筛选
    login_time_start = filters.DateTimeFilter(field_name="created_at", lookup_expr="gte")
    login_time_end = filters.DateTimeFilter(field_name="created_at", lookup_expr="lte")

    # 源IP筛选
    source_ip = filters.CharFilter(field_name="source_ip", lookup_expr="icontains")

    # 地理位置筛选
    location = filters.CharFilter(field_name="location", lookup_expr="icontains")

    # 操作系统筛选
    os_info = filters.CharFilter(field_name="os_info", lookup_expr="icontains")

    # 浏览器筛选
    browser_info = filters.CharFilter(field_name="browser_info", lookup_expr="icontains")

    class Meta:
        model = UserLoginLog
        fields = [
            "status",
            "username",
            "login_time_start",
            "login_time_end",
            "source_ip",
            "location",
            "os_info",
            "browser_info",
        ]


class UserLoginLogViewSet(LanguageViewSet):
    """
    用户登录日志视图集

    提供登录日志的查询和筛选功能，不支持创建、修改、删除操作
    登录日志由系统自动记录
    """

    queryset = UserLoginLog.objects.all().order_by("-created_at")
    serializer_class = UserLoginLogSerializer
    filterset_class = UserLoginLogFilter
    permission_classes = [permissions.IsAuthenticated]

    # 只允许查询操作，不允许创建、修改、删除
    http_method_names = ["get", "head", "options"]

    @action(detail=False, methods=["get"])
    def statistics(self, request):
        """
        获取登录日志统计信息

        返回：
        - total: 总登录次数
        - success_count: 成功登录次数
        - failed_count: 失败登录次数
        - success_rate: 成功率
        """
        # 应用过滤器
        queryset = self.filter_queryset(self.get_queryset())

        total = queryset.count()
        success_count = queryset.filter(status=UserLoginLog.STATUS_SUCCESS).count()
        failed_count = queryset.filter(status=UserLoginLog.STATUS_FAILED).count()

        success_rate = round(success_count / total * 100, 2) if total > 0 else 0

        return Response(
            {
                "total": total,
                "success_count": success_count,
                "failed_count": failed_count,
                "success_rate": success_rate,
            }
        )
