"""定时任务视图"""

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.time_util import get_crontab_next_runs
from apps.core.utils.viewset_utils import AuthViewSet
from apps.job_mgmt.constants import ExecutionStatus, JobType
from apps.job_mgmt.filters.scheduled_task import ScheduledTaskFilter
from apps.job_mgmt.models import JobExecution, ScheduledTask
from apps.job_mgmt.serializers.scheduled_task import (
    ScheduledTaskBatchDeleteSerializer,
    ScheduledTaskCreateSerializer,
    ScheduledTaskDetailSerializer,
    ScheduledTaskListSerializer,
    ScheduledTaskToggleSerializer,
    ScheduledTaskUpdateSerializer,
)
from apps.job_mgmt.services.scheduled_task_service import ScheduledTaskService
from apps.job_mgmt.services.script_params_service import ScriptParamsService
from apps.job_mgmt.tasks import distribute_files_task, execute_playbook_task, execute_script_task


class ScheduledTaskViewSet(AuthViewSet):
    """定时任务视图集"""

    queryset = ScheduledTask.objects.all()
    serializer_class = ScheduledTaskListSerializer
    filterset_class = ScheduledTaskFilter
    search_fields = ["name", "description"]
    ORGANIZATION_FIELD = "team"
    permission_key = "job"

    def get_serializer_class(self):
        if self.action == "retrieve":
            return ScheduledTaskDetailSerializer
        elif self.action == "create":
            return ScheduledTaskCreateSerializer
        elif self.action in ("update", "partial_update"):
            return ScheduledTaskUpdateSerializer
        elif self.action == "toggle":
            return ScheduledTaskToggleSerializer
        elif self.action == "batch_delete":
            return ScheduledTaskBatchDeleteSerializer
        return ScheduledTaskListSerializer

    @HasPermission("cron_task-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("cron_task-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("cron_task-Add")
    def create(self, request, *args, **kwargs):
        serializer = ScheduledTaskCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        return Response(
            ScheduledTaskDetailSerializer(instance).data,
            status=status.HTTP_201_CREATED,
        )

    @HasPermission("cron_task-Edit")
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = ScheduledTaskUpdateSerializer(instance, data=request.data, partial=partial, context={"request": request})
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        return Response(ScheduledTaskDetailSerializer(instance).data)

    @action(detail=True, methods=["post"])
    @HasPermission("cron_task-Edit")
    def toggle(self, request, pk=None):
        """
        启用/禁用定时任务
        """
        instance = self.get_object()
        serializer = ScheduledTaskToggleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        instance.is_enabled = serializer.validated_data["is_enabled"]
        instance.updated_by = request.user.username if request.user else ""
        instance.save(update_fields=["is_enabled", "updated_by", "updated_at"])

        # 同步更新 celery-beat PeriodicTask 的启用状态
        ScheduledTaskService.toggle_periodic_task(instance.id, instance.is_enabled)

        return Response(
            {
                "message": f"任务已{'启用' if instance.is_enabled else '禁用'}",
                "is_enabled": instance.is_enabled,
            }
        )

    @action(detail=True, methods=["post"])
    @HasPermission("cron_task-Edit")
    def run_now(self, request, pk=None):
        """
        立即执行（手动触发一次）

        创建一个 JobExecution 并立即执行
        """
        instance = self.get_object()

        # 获取执行目标
        target_list = instance.target_list or []
        if not target_list:
            return Response({"error": "没有配置执行目标"}, status=status.HTTP_400_BAD_REQUEST)

        # 处理参数：解析 is_modified=False 的参数并转换为字符串
        params = instance.params if isinstance(instance.params, list) else []
        resolved_params = ScriptParamsService.resolve_params(params, script=instance.script)
        params_str = ScriptParamsService.params_to_string(resolved_params)

        # 根据作业类型创建执行记录
        execution = JobExecution.objects.create(
            name=f"[手动触发] {instance.name}",
            job_type=instance.job_type,
            status=ExecutionStatus.PENDING,
            script=instance.script,
            playbook=instance.playbook,
            params=params_str,
            script_type=instance.script_type,
            script_content=instance.script_content,
            files=instance.files,
            target_path=instance.target_path,
            timeout=instance.timeout,
            total_count=len(target_list),
            target_source=instance.target_source,
            target_list=target_list,
            team=instance.team,
            created_by=request.user.username if request.user else "",
            updated_by=request.user.username if request.user else "",
        )

        # 触发异步任务
        if instance.job_type == JobType.SCRIPT:
            execute_script_task.delay(execution.id)
        elif instance.job_type == JobType.FILE_DISTRIBUTION:
            distribute_files_task.delay(execution.id)
        elif instance.job_type == JobType.PLAYBOOK:
            execute_playbook_task.delay(execution.id)

        return Response(
            {
                "message": "已触发执行",
                "execution_id": execution.id,
            }
        )

    @HasPermission("cron_task-Delete")
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()

        # 删除关联的 celery-beat PeriodicTask
        ScheduledTaskService.delete_periodic_task(instance.id)

        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["post"])
    @HasPermission("cron_task-Delete")
    def batch_delete(self, request):
        """
        批量删除定时任务
        """
        serializer = ScheduledTaskBatchDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        ids = serializer.validated_data["ids"]
        tasks = ScheduledTask.objects.filter(id__in=ids)

        # 删除关联的 PeriodicTask
        for task in tasks:
            ScheduledTaskService.delete_periodic_task(task.id)

        deleted_count, _ = tasks.delete()

        return Response(
            {
                "message": f"已删除 {deleted_count} 个定时任务",
                "deleted_count": deleted_count,
            }
        )

    @action(detail=False, methods=["post"], url_path="crontab_preview")
    def crontab_preview(self, request):
        """
        预览   表达式的下次执行时间

        请求参数:
            cron_expression: crontab 表达式 (5字段: 分 时 日 月 周)

        返回:
            next_runs: 下5次执行时间列表
        """
        cron_expression = request.data.get("cron_expression", "").strip()

        if not cron_expression:
            return Response({"error": "cron_expression 不能为空"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            next_runs = get_crontab_next_runs(cron_expression, count=5)
            return Response({"result": True, "data": {"next_runs": next_runs}})
        except ValueError as e:
            return Response({"result": False, "message": str(e)}, status=status.HTTP_400_BAD_REQUEST)
