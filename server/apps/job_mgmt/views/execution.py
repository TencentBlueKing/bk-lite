"""作业执行视图"""

from datetime import datetime

from django_minio_backend import MinioBackend
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import AuthViewSet
from apps.job_mgmt.constants import ExecutionStatus, JobType
from apps.job_mgmt.filters.execution import JobExecutionFilter
from apps.job_mgmt.models import JobExecution, JobExecutionTarget, Playbook, Script, Target
from apps.job_mgmt.serializers.execution import (
    FileDistributionSerializer,
    JobExecutionDetailSerializer,
    JobExecutionListSerializer,
    QuickExecuteSerializer,
)
from apps.job_mgmt.services.dangerous_checker import DangerousChecker
from apps.job_mgmt.services.script_params_service import ScriptParamsService
from apps.job_mgmt.tasks import distribute_files_task, execute_playbook_task, execute_script_task

# 文件分发存储 bucket
FILE_DISTRIBUTION_BUCKET = "job-mgmt-private"


class JobExecutionViewSet(AuthViewSet):
    """作业执行视图集"""

    queryset = JobExecution.objects.all()
    serializer_class = JobExecutionListSerializer
    filterset_class = JobExecutionFilter
    search_fields = ["name"]
    ORGANIZATION_FIELD = "team"
    permission_key = "job"
    http_method_names = ["get", "post"]  # 只允许查看和创建，不允许修改删除

    def get_serializer_class(self):
        if self.action == "retrieve":
            return JobExecutionDetailSerializer
        elif self.action == "quick_execute":
            return QuickExecuteSerializer
        elif self.action == "file_distribution":
            return FileDistributionSerializer
        return JobExecutionListSerializer

    @HasPermission("job_record-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("job_record-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @action(detail=False, methods=["post"])
    @HasPermission("quick_exec-Add")
    def quick_execute(self, request):
        """
        快速执行（统一入口）

        支持三种模式：
        1. 作业模版 - 脚本库：指定 script_id
        2. 作业模版 - Playbook：指定 playbook_id
        3. 临时输入：指定 script_type + script_content
        """
        serializer = QuickExecuteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # 验证目标
        target_ids = data["target_ids"]
        targets = Target.objects.filter(id__in=target_ids)
        if targets.count() != len(target_ids):
            return Response({"error": "部分目标不存在"}, status=status.HTTP_400_BAD_REQUEST)

        username = request.user.username if request.user else ""
        name = data["name"]
        timeout = data.get("timeout", 600)
        team = data.get("team", [])
        params = data.get("params", [])

        # 处理新格式参数：解析 is_modified=False 的参数
        script = None
        if data.get("script_id"):
            script = Script.objects.filter(id=data["script_id"]).first()
        resolved_params = ScriptParamsService.resolve_params(params, script=script)
        params_str = ScriptParamsService.params_to_string(resolved_params)
        # 根据模式创建执行记录
        if data.get("playbook_id"):
            # Playbook 模式
            playbook = Playbook.objects.get(id=data["playbook_id"])
            execution = JobExecution.objects.create(
                name=name,
                job_type=JobType.PLAYBOOK,
                status=ExecutionStatus.PENDING,
                playbook=playbook,
                params=params_str,
                timeout=timeout,
                total_count=len(target_ids),
                team=team,
                created_by=username,
                updated_by=username,
            )
            task_func = execute_playbook_task
        else:
            # 脚本模式（脚本库 或 临时输入）
            script_content = data.get("script_content", "")
            script_type = data.get("script_type", "")

            if data.get("script_id"):
                script = Script.objects.get(id=data["script_id"])
                script_content = script.content
                script_type = script.script_type

            # 高危命令检测
            check_result = DangerousChecker.check_command(script_content, team)
            if not check_result.can_execute:
                forbidden_rules = [r["rule_name"] for r in check_result.forbidden]
                return Response(
                    {"error": f"脚本包含高危命令，禁止执行: {', '.join(forbidden_rules)}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            execution = JobExecution.objects.create(
                name=name,
                job_type=JobType.SCRIPT,
                status=ExecutionStatus.PENDING,
                script=script,
                params=params_str,
                script_type=script_type,
                script_content=script_content,
                timeout=timeout,
                total_count=len(target_ids),
                team=team,
                created_by=username,
                updated_by=username,
            )
            task_func = execute_script_task

        # 创建目标明细
        for target in targets:
            JobExecutionTarget.objects.create(
                execution=execution,
                target=target,
                status=ExecutionStatus.PENDING,
            )

        # 触发异步任务
        task_func.delay(execution.id)

        return Response(
            JobExecutionDetailSerializer(execution).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["post"], parser_classes=[MultiPartParser])
    @HasPermission("file_dist-Add")
    def file_distribution(self, request):
        """
        文件分发

        使用 multipart/form-data 上传文件并分发到指定目标。

        请求体 (multipart/form-data):
        {
            "name": "部署配置文件",
            "files": [<文件1>, <文件2>, ...],
            "target_ids": [1, 2, 3],
            "target_path": "/etc/nginx/",
            "overwrite_strategy": "overwrite",
            "timeout": 600,
            "team": [1]
        }
        """
        serializer = FileDistributionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # 验证目标
        target_ids = data["target_ids"]
        targets = Target.objects.filter(id__in=target_ids)
        if targets.count() != len(target_ids):
            return Response({"error": "部分目标不存在"}, status=status.HTTP_400_BAD_REQUEST)

        username = request.user.username if request.user else ""

        target_path = data["target_path"]
        team = data.get("team", [])

        # 高危路径检测
        check_result = DangerousChecker.check_path(target_path, team)
        if not check_result.can_execute:
            forbidden_rules = [r["rule_name"] for r in check_result.forbidden]
            return Response(
                {"error": f"目标路径为高危路径，禁止分发: {', '.join(forbidden_rules)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 上传文件到 MinIO，构建 files 列表
        storage = MinioBackend(bucket_name=FILE_DISTRIBUTION_BUCKET)
        files_info = []
        for file in data["files"]:
            now = datetime.now()
            file_path = f"files/{now.year}/{now.month:02d}/{now.day:02d}/{file.name}"
            saved_path = storage.save(file_path, file)
            files_info.append(
                {
                    "name": file.name,
                    "file_key": saved_path,
                    "bucket_name": FILE_DISTRIBUTION_BUCKET,
                    "size": file.size,
                }
            )

        # 创建执行记录
        execution = JobExecution.objects.create(
            name=data["name"],
            job_type=JobType.FILE_DISTRIBUTION,
            status=ExecutionStatus.PENDING,
            files=files_info,
            target_path=data["target_path"],
            overwrite_strategy=data.get("overwrite_strategy", "overwrite"),
            timeout=data.get("timeout", 600),
            total_count=len(target_ids),
            team=data.get("team", []),
            created_by=username,
            updated_by=username,
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

    @action(detail=True, methods=["get"])
    @HasPermission("job_record-View")
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
    @HasPermission("job_record-Edit")
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
