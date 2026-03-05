"""定时任务视图"""

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.utils.viewset_utils import AuthViewSet
from apps.job_mgmt.constants import ExecutionStatus, JobType
from apps.job_mgmt.filters.scheduled_task import ScheduledTaskFilter
from apps.job_mgmt.models import JobExecution, JobExecutionTarget, ScheduledTask
from apps.job_mgmt.serializers.scheduled_task import (
    ScheduledTaskBatchDeleteSerializer,
    ScheduledTaskCreateSerializer,
    ScheduledTaskDetailSerializer,
    ScheduledTaskListSerializer,
    ScheduledTaskToggleSerializer,
    ScheduledTaskUpdateSerializer,
)
from apps.job_mgmt.services.scheduled_task_service import ScheduledTaskService
from apps.job_mgmt.tasks import distribute_files_task, execute_playbook_task, execute_script_task


class ScheduledTaskViewSet(AuthViewSet):
    """定时任务视图集"""

    queryset = ScheduledTask.objects.all()
    serializer_class = ScheduledTaskListSerializer
    filterset_class = ScheduledTaskFilter
    search_fields = ["name", "description"]
    ORGANIZATION_FIELD = "team"

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

    def create(self, request, *args, **kwargs):
        serializer = ScheduledTaskCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        return Response(
            ScheduledTaskDetailSerializer(instance).data,
            status=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = ScheduledTaskUpdateSerializer(instance, data=request.data, partial=partial, context={"request": request})
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        return Response(ScheduledTaskDetailSerializer(instance).data)

    @action(detail=True, methods=["post"])
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
    def run_now(self, request, pk=None):
        """
        立即执行（手动触发一次）

        创建一个 JobExecution 并立即执行
        """
        instance = self.get_object()

        # 获取执行目标
        targets = list(instance.targets.all())
        if not targets:
            return Response({"error": "没有配置执行目标"}, status=status.HTTP_400_BAD_REQUEST)

        # 根据作业类型创建执行记录
        execution = JobExecution.objects.create(
            name=f"[手动触发] {instance.name}",
            job_type=instance.job_type,
            status=ExecutionStatus.PENDING,
            script=instance.script,
            playbook=instance.playbook,
            params=instance.params,
            script_type=instance.script_type,
            script_content=instance.script_content,
            files=instance.files,
            target_path=instance.target_path,
            timeout=instance.timeout,
            total_count=len(targets),
            team=instance.team,
            created_by=request.user.username if request.user else "",
            updated_by=request.user.username if request.user else "",
        )

        # 创建目标明细
        for target in targets:
            JobExecutionTarget.objects.create(
                execution=execution,
                target=target,
                status=ExecutionStatus.PENDING,
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

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()

        # 删除关联的 celery-beat PeriodicTask
        ScheduledTaskService.delete_periodic_task(instance.id)

        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["post"])
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
