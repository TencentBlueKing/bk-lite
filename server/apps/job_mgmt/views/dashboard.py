"""Dashboard视图"""

from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from apps.job_mgmt.constants import ExecutionStatus
from apps.job_mgmt.models import JobExecution, Playbook, ScheduledTask, Script, Target
from apps.job_mgmt.serializers.dashboard import DashboardRecentExecutionSerializer, DashboardStatsSerializer, DashboardTrendSerializer


class DashboardViewSet(ViewSet):
    """Dashboard视图集"""

    @action(detail=False, methods=["get"])
    def stats(self, request):
        """
        获取Dashboard统计数据
        """
        # 目标统计
        target_total = Target.objects.count()
        target_online = Target.objects.filter(is_online=True).count()
        target_offline = target_total - target_online

        # 脚本/Playbook统计
        script_total = Script.objects.count()
        playbook_total = Playbook.objects.count()

        # 执行统计
        execution_total = JobExecution.objects.count()
        execution_success = JobExecution.objects.filter(status=ExecutionStatus.SUCCESS).count()
        execution_failed = JobExecution.objects.filter(status=ExecutionStatus.FAILED).count()
        execution_running = JobExecution.objects.filter(status=ExecutionStatus.RUNNING).count()

        # 定时任务统计
        scheduled_task_total = ScheduledTask.objects.count()
        scheduled_task_enabled = ScheduledTask.objects.filter(is_enabled=True).count()

        data = {
            "target_total": target_total,
            "target_online": target_online,
            "target_offline": target_offline,
            "script_total": script_total,
            "playbook_total": playbook_total,
            "execution_total": execution_total,
            "execution_success": execution_success,
            "execution_failed": execution_failed,
            "execution_running": execution_running,
            "scheduled_task_total": scheduled_task_total,
            "scheduled_task_enabled": scheduled_task_enabled,
        }

        serializer = DashboardStatsSerializer(data)
        return Response(serializer.data)

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
    def recent_executions(self, request):
        """
        获取最近执行记录
        """
        limit = int(request.query_params.get("limit", 10))
        limit = min(limit, 50)  # 最多50条

        executions = JobExecution.objects.order_by("-created_at")[:limit]

        result = []
        for execution in executions:
            result.append(
                {
                    "id": execution.id,
                    "name": execution.name,
                    "job_type": execution.job_type,
                    "job_type_display": execution.get_job_type_display(),
                    "status": execution.status,
                    "status_display": execution.get_status_display(),
                    "created_by": execution.created_by,
                    "created_at": execution.created_at,
                }
            )

        serializer = DashboardRecentExecutionSerializer(result, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def job_type_distribution(self, request):
        """
        获取作业类型分布
        """
        distribution = JobExecution.objects.values("job_type").annotate(count=Count("id")).order_by("-count")

        from apps.job_mgmt.constants import JobType

        job_type_names = dict(JobType.CHOICES)

        result = []
        for item in distribution:
            result.append(
                {
                    "job_type": item["job_type"],
                    "job_type_display": job_type_names.get(item["job_type"], item["job_type"]),
                    "count": item["count"],
                }
            )

        return Response(result)

    @action(detail=False, methods=["get"])
    def execution_status_distribution(self, request):
        """
        获取执行状态分布
        """
        distribution = JobExecution.objects.values("status").annotate(count=Count("id")).order_by("-count")

        status_names = dict(ExecutionStatus.CHOICES)

        result = []
        for item in distribution:
            result.append(
                {
                    "status": item["status"],
                    "status_display": status_names.get(item["status"], item["status"]),
                    "count": item["count"],
                }
            )

        return Response(result)

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
