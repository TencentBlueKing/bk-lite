"""作业执行视图"""

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import AuthViewSet
from apps.job_mgmt.constants import ExecutionStatus, JobType, TargetSource, TriggerSource
from apps.job_mgmt.filters.execution import JobExecutionFilter
from apps.job_mgmt.models import DistributionFile, JobExecution, Playbook, Script, Target
from apps.job_mgmt.serializers.execution import (
    FileDistributionSerializer,
    JobExecutionDetailSerializer,
    JobExecutionListSerializer,
    QuickExecuteSerializer,
)
from apps.job_mgmt.services.dangerous_checker import DangerousChecker
from apps.job_mgmt.services.script_params_service import ScriptParamsService
from apps.job_mgmt.tasks import distribute_files_task, execute_playbook_task, execute_script_task


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

        # 获取目标来源和目标列表
        target_source = data["target_source"]
        target_list = data["target_list"]

        # 验证目标（仅 manual 来源需要验证 target_id 存在）
        if target_source == TargetSource.MANUAL:
            target_ids = [t.get("target_id") for t in target_list if t.get("target_id")]
            if target_ids:
                existing_count = Target.objects.filter(id__in=target_ids).count()
                if existing_count != len(target_ids):
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
                total_count=len(target_list),
                target_source=target_source,
                target_list=target_list,
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
                total_count=len(target_list),
                target_source=target_source,
                target_list=target_list,
                team=team,
                created_by=username,
                updated_by=username,
            )
            task_func = execute_script_task

        # 触发异步任务
        # task_func.delay(execution.id)
        task_func(execution.id)

        return Response(
            JobExecutionDetailSerializer(execution).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["post"])
    @HasPermission("file_dist-Add")
    def file_distribution(self, request):
        """
        文件分发

        使用 JSON 请求体，传入已上传文件的 ID 列表进行分发。

        请求体 (application/json):
        {
            "name": "部署配置文件",
            "file_ids": [1, 2, 3],
            "target_source": "node_mgmt",
            "target_list": [{"node_id": "xxx", "name": "xxx", "ip": "1.2.3.4", "os": "linux"}],
            "target_path": "/etc/nginx/",
            "overwrite_strategy": "overwrite",
            "timeout": 600,
            "team": [1]
        }
        """
        serializer = FileDistributionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # 获取目标来源和目标列表
        target_source = data["target_source"]
        target_list = data["target_list"]

        # 验证目标（仅 manual 来源需要验证 target_id 存在）
        if target_source == TargetSource.MANUAL:
            target_ids = [t.get("target_id") for t in target_list if t.get("target_id")]
            if target_ids:
                existing_count = Target.objects.filter(id__in=target_ids).count()
                if existing_count != len(target_ids):
                    return Response({"error": "部分目标不存在"}, status=status.HTTP_400_BAD_REQUEST)

        # 验证文件
        file_ids = data["file_ids"]
        distribution_files = DistributionFile.objects.filter(id__in=file_ids)
        if distribution_files.count() != len(file_ids):
            return Response({"error": "部分文件不存在或已过期"}, status=status.HTTP_400_BAD_REQUEST)

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

        # 从数据库获取文件信息，构建 files 列表
        files_info = []
        for df in distribution_files:
            files_info.append(
                {
                    "name": df.original_name,
                    "file_key": df.file_key,
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
            total_count=len(target_list),
            target_source=target_source,
            target_list=target_list,
            team=data.get("team", []),
            created_by=username,
            updated_by=username,
        )

        # 触发异步任务
        # distribute_files_task.delay(execution.id)
        distribute_files_task(execution.id)

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
        execution = self.get_object()
        return Response(execution.execution_results or [])

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

        return Response({"message": "已取消执行"})

    @action(detail=True, methods=["post"])
    @HasPermission("job_record-Edit")
    def re_execute(self, request, pk=None):
        """
        重新执行

        基于现有执行记录创建一个新的执行任务，使用相同的参数重新执行。
        """
        original = self.get_object()

        username = request.user.username if request.user else ""

        # 获取原执行记录的目标列表
        target_list = original.target_list or []
        if not target_list:
            return Response({"error": "原执行目标已不存在"}, status=status.HTTP_400_BAD_REQUEST)

        # 根据作业类型创建新的执行记录
        if original.job_type == JobType.FILE_DISTRIBUTION:
            execution = JobExecution.objects.create(
                name=original.name,
                job_type=JobType.FILE_DISTRIBUTION,
                trigger_source=TriggerSource.MANUAL,
                status=ExecutionStatus.PENDING,
                files=original.files,
                target_path=original.target_path,
                overwrite_strategy=original.overwrite_strategy,
                timeout=original.timeout,
                total_count=len(target_list),
                target_source=original.target_source,
                target_list=target_list,
                team=original.team,
                created_by=username,
                updated_by=username,
            )
            task_func = distribute_files_task
        elif original.job_type == JobType.PLAYBOOK:
            if not original.playbook:
                return Response({"error": "原关联 Playbook 已不存在"}, status=status.HTTP_400_BAD_REQUEST)

            # 高危命令检测（Playbook 内容可能已变更）
            # Playbook 暂不做高危检测

            execution = JobExecution.objects.create(
                name=original.name,
                job_type=JobType.PLAYBOOK,
                trigger_source=TriggerSource.MANUAL,
                status=ExecutionStatus.PENDING,
                playbook=original.playbook,
                params=original.params,
                timeout=original.timeout,
                total_count=len(target_list),
                target_source=original.target_source,
                target_list=target_list,
                team=original.team,
                created_by=username,
                updated_by=username,
            )
            task_func = execute_playbook_task
        else:
            # 脚本执行
            # 高危命令检测
            check_result = DangerousChecker.check_command(original.script_content, original.team)
            if not check_result.can_execute:
                forbidden_rules = [r["rule_name"] for r in check_result.forbidden]
                return Response(
                    {"error": f"脚本包含高危命令，禁止执行: {', '.join(forbidden_rules)}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            execution = JobExecution.objects.create(
                name=original.name,
                job_type=JobType.SCRIPT,
                trigger_source=TriggerSource.MANUAL,
                status=ExecutionStatus.PENDING,
                script=original.script,
                params=original.params,
                script_type=original.script_type,
                script_content=original.script_content,
                timeout=original.timeout,
                total_count=len(target_list),
                target_source=original.target_source,
                target_list=target_list,
                team=original.team,
                created_by=username,
                updated_by=username,
            )
            task_func = execute_script_task

        # 触发异步任务
        task_func.delay(execution.id)

        return Response(
            JobExecutionDetailSerializer(execution).data,
            status=status.HTTP_201_CREATED,
        )
