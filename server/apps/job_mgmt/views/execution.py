"""作业执行视图"""

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.utils.viewset_utils import AuthViewSet
from apps.job_mgmt.constants import ExecutionStatus, JobType
from apps.job_mgmt.filters.execution import JobExecutionFilter
from apps.job_mgmt.models import JobExecution, JobExecutionTarget, Playbook, Script, Target
from apps.job_mgmt.serializers.execution import (
    FileDistributionSerializer,
    JobExecutionDetailSerializer,
    JobExecutionListSerializer,
    PlaybookExecuteSerializer,
    QuickExecuteSerializer,
)
from apps.job_mgmt.tasks import distribute_files_task, execute_playbook_task, execute_script_task


class JobExecutionViewSet(AuthViewSet):
    """作业执行视图集"""

    queryset = JobExecution.objects.all()
    serializer_class = JobExecutionListSerializer
    filterset_class = JobExecutionFilter
    search_fields = ["name"]
    ORGANIZATION_FIELD = "team"
    http_method_names = ["get", "post"]  # 只允许查看和创建，不允许修改删除

    def get_serializer_class(self):
        if self.action == "retrieve":
            return JobExecutionDetailSerializer
        elif self.action == "quick_execute":
            return QuickExecuteSerializer
        elif self.action == "file_distribution":
            return FileDistributionSerializer
        elif self.action == "playbook_execute":
            return PlaybookExecuteSerializer
        return JobExecutionListSerializer

    @action(detail=False, methods=["post"])
    def quick_execute(self, request):
        """
        快速执行脚本

        支持两种方式：
        1. 指定 script_id 使用已有脚本
        2. 直接传入 script_content 执行临时脚本
        """
        serializer = QuickExecuteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # 获取脚本信息
        script = None
        script_content = data.get("script_content", "")
        script_type = data.get("script_type", "")

        if data.get("script_id"):
            script = Script.objects.filter(id=data["script_id"]).first()
            if not script:
                return Response({"error": "脚本不存在"}, status=status.HTTP_400_BAD_REQUEST)
            script_content = script.content
            script_type = script.script_type

        # 验证目标
        target_ids = data["target_ids"]
        targets = Target.objects.filter(id__in=target_ids)
        if targets.count() != len(target_ids):
            return Response({"error": "部分目标不存在"}, status=status.HTTP_400_BAD_REQUEST)

        # 创建执行记录
        name = data.get("name") or f"快速执行-{script.name if script else '临时脚本'}"
        execution = JobExecution.objects.create(
            name=name,
            job_type=JobType.SCRIPT,
            status=ExecutionStatus.PENDING,
            script=script,
            params=data.get("params", {}),
            script_type=script_type,
            script_content=script_content,
            timeout=data.get("timeout", 60),
            total_count=len(target_ids),
            team=data.get("team", []),
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
        execute_script_task.delay(execution.id)

        return Response(
            JobExecutionDetailSerializer(execution).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["post"])
    def file_distribution(self, request):
        """
        文件分发

        将文件分发到指定目标
        """
        serializer = FileDistributionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # 验证目标
        target_ids = data["target_ids"]
        targets = Target.objects.filter(id__in=target_ids)
        if targets.count() != len(target_ids):
            return Response({"error": "部分目标不存在"}, status=status.HTTP_400_BAD_REQUEST)

        # 创建执行记录
        name = data.get("name") or f"文件分发-{len(data['files'])}个文件"
        execution = JobExecution.objects.create(
            name=name,
            job_type=JobType.FILE_DISTRIBUTION,
            status=ExecutionStatus.PENDING,
            files=data["files"],
            target_path=data["target_path"],
            timeout=data.get("timeout", 300),
            total_count=len(target_ids),
            team=data.get("team", []),
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
        distribute_files_task.delay(execution.id)

        return Response(
            JobExecutionDetailSerializer(execution).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["post"])
    def playbook_execute(self, request):
        """
        执行 Playbook
        """
        serializer = PlaybookExecuteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # 获取 Playbook
        playbook = Playbook.objects.filter(id=data["playbook_id"]).first()
        if not playbook:
            return Response({"error": "Playbook不存在"}, status=status.HTTP_400_BAD_REQUEST)

        # 验证目标
        target_ids = data["target_ids"]
        targets = Target.objects.filter(id__in=target_ids)
        if targets.count() != len(target_ids):
            return Response({"error": "部分目标不存在"}, status=status.HTTP_400_BAD_REQUEST)

        # 创建执行记录
        name = data.get("name") or f"Playbook执行-{playbook.name}"
        execution = JobExecution.objects.create(
            name=name,
            job_type=JobType.PLAYBOOK,
            status=ExecutionStatus.PENDING,
            playbook=playbook,
            params=data.get("params", {}),
            timeout=data.get("timeout", 300),
            total_count=len(target_ids),
            team=data.get("team", []),
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
        execute_playbook_task.delay(execution.id)

        return Response(
            JobExecutionDetailSerializer(execution).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["get"])
    def targets(self, request, pk=None):
        """
        获取执行目标明细列表
        """
        from apps.job_mgmt.serializers.execution import JobExecutionTargetSerializer

        execution = self.get_object()
        targets = execution.execution_targets.all()
        serializer = JobExecutionTargetSerializer(targets, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        """
        取消执行（仅限等待中或执行中的任务）
        """
        execution = self.get_object()

        if execution.status in ExecutionStatus.TERMINAL_STATES:
            return Response(
                {"error": f"任务已处于终态({execution.get_status_display()})，无法取消"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 更新状态
        execution.status = ExecutionStatus.CANCELLED
        execution.save(update_fields=["status", "updated_at"])

        # 更新所有未完成的目标
        execution.execution_targets.exclude(status__in=ExecutionStatus.TERMINAL_STATES).update(status=ExecutionStatus.CANCELLED)

        return Response({"message": "已取消执行"})
