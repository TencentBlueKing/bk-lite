"""Dashboard视图"""

from datetime import date, timedelta

from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Q
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import AuthViewSet
from apps.job_mgmt.constants import ExecutionStatus, JobType
from apps.job_mgmt.models import JobExecution, Playbook, ScheduledTask, Script, Target
from apps.job_mgmt.serializers.dashboard import DashboardStatsSerializer, DashboardTrendSerializer

# 统计时间范围常量
DEFAULT_RANGE_DAYS = 7  # days 默认值（近一周）
MAX_DAYS_PARAM = 30  # days 参数上限
MAX_RANGE_DAYS = 90  # 自定义区间最大跨度（闭区间天数）


def _resolve_date_range(request):
    """解析统计时间范围，返回 ``(start_date, end_date, error)``。

    - 自定义区间：同时提供 ``start_date`` / ``end_date``（``YYYY-MM-DD``，闭区间）。
      未来的 ``end`` 裁剪到今天；校验格式、顺序、跨度上限、是否全在未来。
    - 否则按 ``days`` 回退（默认 :data:`DEFAULT_RANGE_DAYS`，上限 :data:`MAX_DAYS_PARAM`，
      非法值回退默认）。
    出错时 ``error`` 为提示字符串、``start``/``end`` 为 ``None``。
    """
    today = timezone.localdate()
    params = request.query_params
    start_raw = params.get("start_date")
    end_raw = params.get("end_date")

    # 自定义区间
    if start_raw or end_raw:
        if not (start_raw and end_raw):
            return None, None, "start_date 与 end_date 必须同时提供"
        try:
            start_date = date.fromisoformat(start_raw)
            end_date = date.fromisoformat(end_raw)
        except ValueError:
            return None, None, "日期格式无效，应为 YYYY-MM-DD"

        # 未来的结束日期裁剪到今天
        if end_date > today:
            end_date = today
        if start_date > today:
            return None, None, "时间范围不能全部在未来"
        if start_date > end_date:
            return None, None, "start_date 不能晚于 end_date"
        if (end_date - start_date).days + 1 > MAX_RANGE_DAYS:
            return None, None, f"时间范围不能超过 {MAX_RANGE_DAYS} 天"
        return start_date, end_date, None

    # days 回退
    try:
        days = int(params.get("days", DEFAULT_RANGE_DAYS))
    except (TypeError, ValueError):
        days = DEFAULT_RANGE_DAYS
    if days < 1:
        days = DEFAULT_RANGE_DAYS
    days = min(days, MAX_DAYS_PARAM)

    end_date = today
    start_date = today - timedelta(days=days - 1)
    return start_date, end_date, None


# 执行时长表达式：finished_at - started_at（仅对有完整起止时间的执行有效）
DURATION_EXPR = ExpressionWrapper(F("finished_at") - F("started_at"), output_field=DurationField())


def _duration_to_seconds(value):
    """timedelta -> 秒（保留 1 位小数）；None -> 0"""
    return round(value.total_seconds(), 1) if value else 0


class DashboardViewSet(AuthViewSet):
    """Dashboard视图集"""

    ORGANIZATION_FIELD = "team"
    permission_key = "job"

    def _get_team_filter(self, request):
        """返回当前用户可见的 team 过滤条件。

        超级管理员不做 team 过滤（返回全量）；普通用户只能看当前 team 的数据。
        """
        if getattr(request.user, "is_superuser", False):
            return Q()
        current_team = self._validate_current_team_permission(request)
        return Q(team__contains=current_team)

    @HasPermission("job_record-View")
    @action(detail=False, methods=["get"])
    def trend(self, request):
        """获取执行趋势数据（按 days 或自定义 start_date/end_date 闭区间）"""
        start_date, end_date, error = _resolve_date_range(request)
        if error:
            return Response({"error": error}, status=status.HTTP_400_BAD_REQUEST)

        team_filter = self._get_team_filter(request)

        # 按日期分组统计
        executions = (
            JobExecution.objects.filter(
                team_filter,
                created_at__date__gte=start_date,
                created_at__date__lte=end_date,
            )
            .values("created_at__date")
            .annotate(
                execution_count=Count("id"),
                success_count=Count("id", filter=Q(status=ExecutionStatus.SUCCESS)),
                failed_count=Count("id", filter=Q(status=ExecutionStatus.FAILED)),
                cancelled_count=Count("id", filter=Q(status=ExecutionStatus.CANCELLED)),
                avg_duration=Avg(DURATION_EXPR, filter=Q(started_at__isnull=False, finished_at__isnull=False)),
            )
            .order_by("created_at__date")
        )

        # 构建完整的日期序列（缺失日期补 0）
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
                    "cancelled_count": item.get("cancelled_count", 0),
                    "avg_duration_seconds": _duration_to_seconds(item.get("avg_duration")),
                }
            )
            current_date += timedelta(days=1)

        serializer = DashboardTrendSerializer(result, many=True)
        return Response(serializer.data)

    @HasPermission("job_record-View")
    @action(detail=False, methods=["get"])
    def success_rate_compare(self, request):
        """获取当前周期成功率及与上一等长周期对比（支持 days 或自定义区间）"""
        start_date, end_date, error = _resolve_date_range(request)
        if error:
            return Response({"error": error}, status=status.HTTP_400_BAD_REQUEST)

        days = (end_date - start_date).days + 1
        previous_end = start_date - timedelta(days=1)
        previous_start = start_date - timedelta(days=days)

        team_filter = self._get_team_filter(request)

        # 每个周期一次聚合（含条件计数）
        current_stats = JobExecution.objects.filter(team_filter, created_at__date__gte=start_date, created_at__date__lte=end_date).aggregate(
            total=Count("id"),
            success=Count("id", filter=Q(status=ExecutionStatus.SUCCESS)),
            failed=Count("id", filter=Q(status=ExecutionStatus.FAILED)),
            avg_duration=Avg(DURATION_EXPR, filter=Q(started_at__isnull=False, finished_at__isnull=False)),
        )
        previous_stats = JobExecution.objects.filter(team_filter, created_at__date__gte=previous_start, created_at__date__lte=previous_end).aggregate(
            total=Count("id"),
            success=Count("id", filter=Q(status=ExecutionStatus.SUCCESS)),
        )

        current_total = current_stats["total"]
        current_success = current_stats["success"]
        current_failed = current_stats["failed"]
        current_success_rate = round((current_success / current_total * 100) if current_total else 0, 2)

        previous_total = previous_stats["total"]
        previous_success = previous_stats["success"]
        previous_success_rate = round((previous_success / previous_total * 100) if previous_total else 0, 2)

        success_rate_increase = round(current_success_rate - previous_success_rate, 2) if previous_total else current_success_rate

        return Response(
            {
                "current_period": {
                    "execution_total": current_total,
                    "success_count": current_success,
                    "failed_count": current_failed,
                    "success_rate": current_success_rate,
                    "avg_duration_seconds": _duration_to_seconds(current_stats["avg_duration"]),
                },
                "success_rate_increase": success_rate_increase,
                "days": days,
            }
        )

    @action(detail=False, methods=["get"])
    def stats(self, request):
        """获取Dashboard统计数据（资产与执行计数）"""
        # 平均执行时长：仅统计 started_at/finished_at 都有的已完成执行
        execution_stats = JobExecution.objects.aggregate(
            total=Count("id"),
            success=Count("id", filter=Q(status=ExecutionStatus.SUCCESS)),
            failed=Count("id", filter=Q(status=ExecutionStatus.FAILED)),
            running=Count("id", filter=Q(status=ExecutionStatus.RUNNING)),
            pending=Count("id", filter=Q(status=ExecutionStatus.PENDING)),
            avg_duration=Avg(DURATION_EXPR, filter=Q(started_at__isnull=False, finished_at__isnull=False)),
        )
        avg_duration_seconds = _duration_to_seconds(execution_stats["avg_duration"])

        data = {
            "target_total": Target.objects.count(),
            "script_total": Script.objects.count(),
            "playbook_total": Playbook.objects.count(),
            "execution_total": execution_stats["total"],
            "execution_success": execution_stats["success"],
            "execution_failed": execution_stats["failed"],
            "execution_running": execution_stats["running"],
            "execution_pending": execution_stats["pending"],
            "scheduled_task_total": ScheduledTask.objects.count(),
            "scheduled_task_enabled": ScheduledTask.objects.filter(is_enabled=True).count(),
            "avg_duration_seconds": avg_duration_seconds,
        }

        serializer = DashboardStatsSerializer(data)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def job_type_distribution(self, request):
        """获取作业类型分布"""
        distribution = JobExecution.objects.values("job_type").annotate(count=Count("id")).order_by("-count")
        job_type_names = dict(JobType.CHOICES)

        result = [
            {
                "job_type": item["job_type"],
                "job_type_display": job_type_names.get(item["job_type"], item["job_type"]),
                "count": item["count"],
            }
            for item in distribution
        ]
        return Response(result)

    @action(detail=False, methods=["get"])
    def execution_status_distribution(self, request):
        """获取执行状态分布（按 days 或自定义 start_date/end_date 闭区间）"""
        start_date, end_date, error = _resolve_date_range(request)
        if error:
            return Response({"error": error}, status=status.HTTP_400_BAD_REQUEST)
        distribution = (
            JobExecution.objects.filter(created_at__date__gte=start_date, created_at__date__lte=end_date)
            .values("status")
            .annotate(count=Count("id"))
            .order_by("-count")
        )
        status_names = dict(ExecutionStatus.CHOICES)

        result = [
            {
                "status": item["status"],
                "status_display": status_names.get(item["status"], item["status"]),
                "count": item["count"],
            }
            for item in distribution
        ]
        return Response(result)
