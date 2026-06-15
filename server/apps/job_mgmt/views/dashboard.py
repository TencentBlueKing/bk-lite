"""Dashboard视图"""

from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from apps.job_mgmt.constants import ExecutionStatus
from apps.job_mgmt.models import JobExecution
from apps.job_mgmt.serializers.dashboard import DashboardTrendSerializer


class DashboardViewSet(ViewSet):
    """Dashboard视图集"""

    @action(detail=False, methods=["get"])
    def trend(self, request):
        """
        获取执行趋势数据（最近7天）
        """
        days = int(request.query_params.get("days", 7))
        days = min(days, 30)  # 最多30天

        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=days - 1)

        # 按日期分组统计
        executions = (
            JobExecution.objects.filter(
                created_at__date__gte=start_date,
                created_at__date__lte=end_date,
            )
            .values("created_at__date")
            .annotate(
                execution_count=Count("id"),
                success_count=Count("id", filter=Q(status=ExecutionStatus.SUCCESS)),
                failed_count=Count("id", filter=Q(status=ExecutionStatus.FAILED)),
            )
            .order_by("created_at__date")
        )

        # 构建完整的日期序列
        execution_map = {item["created_at__date"]: item for item in executions}
        result = []
        current_date = start_date
        while current_date <= end_date:
            item = execution_map.get(current_date, {})
            result.append(
                {
                    "date": current_date,
                    "execution_count": item.get("execution_count", 0),
                    "success_count": item.get("success_count", 0),
                    "failed_count": item.get("failed_count", 0),
                }
            )
            current_date += timedelta(days=1)

        serializer = DashboardTrendSerializer(result, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def success_rate_compare(self, request):
        """获取当前周期成功率及与上周期对比"""
        days = int(request.query_params.get("days", 7))
        if days not in (7, 30):
            days = 7

        now = timezone.now()
        current_start = now - timedelta(days=days)
        previous_start = current_start - timedelta(days=days)

        current_qs = JobExecution.objects.filter(created_at__gte=current_start, created_at__lt=now)
        previous_qs = JobExecution.objects.filter(created_at__gte=previous_start, created_at__lt=current_start)

        current_total = current_qs.count()
        current_success = current_qs.filter(status=ExecutionStatus.SUCCESS).count()
        current_failed = current_qs.filter(status=ExecutionStatus.FAILED).count()
        current_success_rate = round((current_success / current_total * 100) if current_total else 0, 2)

        previous_total = previous_qs.count()
        previous_success = previous_qs.filter(status=ExecutionStatus.SUCCESS).count()
        previous_success_rate = round((previous_success / previous_total * 100) if previous_total else 0, 2)

        success_rate_increase = round(current_success_rate - previous_success_rate, 2) if previous_total else current_success_rate

        return Response(
            {
                "current_period": {
                    "execution_total": current_total,
                    "success_count": current_success,
                    "failed_count": current_failed,
                    "success_rate": current_success_rate,
                },
                "success_rate_increase": success_rate_increase,
            }
        )
