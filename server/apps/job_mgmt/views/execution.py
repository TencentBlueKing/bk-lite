"""作业执行视图"""

from celery import current_app
from django.http import StreamingHttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.core.logger import job_logger as logger
from apps.core.utils.viewset_utils import AuthViewSet
from apps.job_mgmt.constants import ExecutionStatus
from apps.job_mgmt.filters.execution import JobExecutionFilter
from apps.job_mgmt.models import JobExecution
from apps.job_mgmt.serializers.execution import (
    FileDistributionSerializer,
    JobExecutionDetailSerializer,
    JobExecutionListSerializer,
    QuickExecuteSerializer,
)
from apps.job_mgmt.services.execution_service import ExecutionAuthorizationError, ExecutionDispatchError, ExecutionService
from apps.job_mgmt.services.execution_stream_service import (
    JOB_LOG_MAX_AGE_SECONDS,
    JOB_LOG_MAX_BYTES,
    JOB_LOG_STREAM_NAME,
    JOB_LOG_SUBJECTS,
    snapshot_sse_from_results,
    stream_execution_events,
)
from apps.job_mgmt.tasks import finalize_cancelling_execution
from apps.job_mgmt.utils.team_authz import normalize_authorized_team_ids
from apps.system_mgmt.utils.operation_log_utils import log_operation
from nats_client.clients import ensure_stream_sync

# CANCELLING 兜底收敛任务的额外缓冲（秒）：在 execution.timeout 之后再等一段时间，
# 给真实结果回写留出余量，仍未回写才强制收敛为 CANCELLED。
CANCEL_CONVERGE_BUFFER_SECONDS = 60


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

    def _get_authorized_team_ids(self, request):
        """当前用户有权访问的团队 ID 集合；超管返回 None（不做团队归属限制）。

        用于 quick_execute / file_distribution 在按 ID 加载 Script / Playbook /
        Target / DistributionFile 后校验对象归属，防止跨团队越权引用（BL-NEW-002）。
        """
        user = getattr(request, "user", None)
        if getattr(user, "is_superuser", False):
            return None
        return normalize_authorized_team_ids(getattr(user, "group_list", []))

    def _resolve_execution_team(self, request, data):
        """确定本次执行归属的 team，并校验用户对其有权限。

        - 请求体显式传 team：必须全部落在用户可管理范围内，否则 PermissionDenied。
        - 未传 team：回退到已校验权限的 current_team。
        禁止信任请求体 team 越权指定他人团队（BL-NEW-002）。
        """
        current_team = self._validate_current_team_permission(request)
        requested_team = data.get("team", [])
        if requested_team:
            self._validate_org_field_permission(request, requested_team)
            return requested_team
        return [current_team]

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

        # BL-NEW-002：禁止信任请求体 team 越权；按服务端授权 team 校验所引用对象。
        authorized_team_ids = self._get_authorized_team_ids(request)
        team = self._resolve_execution_team(request, data)
        username = request.user.username if request.user else ""

        try:
            execution = ExecutionService.create_quick_execution(
                data=data,
                team=team,
                authorized_team_ids=authorized_team_ids,
                username=username,
                timeout_explicit="timeout" in request.data,
            )
        except (ExecutionAuthorizationError, ExecutionDispatchError) as e:
            return Response({"error": e.message}, status=e.status_code)

        playbook_name = execution.playbook.name if execution.playbook_id else execution.name
        log_operation(request, "execute", "job", f"快速执行作业: {playbook_name}")

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

        # BL-NEW-002：禁止信任请求体 team 越权；按服务端授权 team 校验所引用对象。
        authorized_team_ids = self._get_authorized_team_ids(request)
        team = self._resolve_execution_team(request, data)
        username = request.user.username if request.user else ""

        try:
            execution = ExecutionService.create_file_distribution(
                data=data,
                team=team,
                authorized_team_ids=authorized_team_ids,
                username=username,
            )
        except (ExecutionAuthorizationError, ExecutionDispatchError) as e:
            return Response({"error": e.message}, status=e.status_code)

        log_operation(request, "execute", "job", "文件分发")

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

    @action(detail=True, methods=["get"])
    @HasPermission("job_record-View")
    def stream(self, request, pk=None):
        """SSE 实时流式输出：非终态走 JetStream 实时回放+tail，终态走结果快照。"""
        execution = self.get_object()
        target_keys = [(t.get("node_id") or str(t.get("target_id", ""))) for t in (execution.target_list or [])]

        if execution.status in ExecutionStatus.TERMINAL_STATES:
            logger.info(
                "[stream] SSE 连接(终态快照): execution_id=%s status=%s targets=%s",
                execution.id,
                execution.status,
                target_keys,
            )
            generator = snapshot_sse_from_results(execution.execution_results or [])
        else:
            logger.info(
                "[stream] SSE 连接(实时): execution_id=%s status=%s targets=%s",
                execution.id,
                execution.status,
                target_keys,
            )
            try:
                ensure_stream_sync(JOB_LOG_STREAM_NAME, JOB_LOG_SUBJECTS, JOB_LOG_MAX_AGE_SECONDS, JOB_LOG_MAX_BYTES)
            except Exception as e:
                logger.warning(f"[stream] JetStream 流声明失败(降级继续): execution_id={execution.id}, error={e}")
            generator = stream_execution_events(execution.id, target_keys)

        response = StreamingHttpResponse(generator, content_type="text/event-stream")
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response

    @action(detail=True, methods=["post"])
    @HasPermission("job_record-Edit")
    def cancel(self, request, pk=None):
        """
        取消执行（按当前状态 CAS 分流，消除竞态与"假取消"）

        - PENDING：worker 尚未取走，CAS 直接置 CANCELLED 终态；
        - RUNNING：已在执行，CAS 置 CANCELLING 过渡态（非终态，等真实结果回写后收敛为
          CANCELLED），并调度兜底收敛任务；Runner 检查点会据此停止后续目标；
        - 终态 / 取消中：拒绝（400）；
        - CAS 未命中（状态被并发改变）：按最新状态拒绝（400）。

        L0: 无论 PENDING/RUNNING，都尽力 revoke 队列中尚未取走的 Celery 任务（失败不阻断）。
        """
        execution = self.get_object()
        status_now = execution.status

        if status_now in ExecutionStatus.TERMINAL_STATES:
            return Response(
                {"error": f"任务已处于终态({execution.get_status_display()})，无法取消"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if status_now == ExecutionStatus.CANCELLING:
            return Response(
                {"error": "任务正在取消中，请勿重复操作"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # L0: 尽力 revoke Celery 任务（仅对队列中尚未被 worker 取走的任务有效；失败不阻断取消）
        if execution.celery_task_id:
            try:
                current_app.control.revoke(execution.celery_task_id)
                logger.info(f"[cancel] 已 revoke Celery 任务: execution_id={execution.id}, task_id={execution.celery_task_id}")
            except Exception as e:
                logger.warning(f"[cancel] revoke Celery 任务失败: execution_id={execution.id}, error={e}")

        now = timezone.now()
        if status_now == ExecutionStatus.PENDING:
            # PENDING→CANCELLED：worker 尚未执行，直接落终态
            updated = JobExecution.objects.filter(id=pk, status=ExecutionStatus.PENDING).update(
                status=ExecutionStatus.CANCELLED, finished_at=now, updated_at=now
            )
            if updated:
                logger.info(f"[cancel] 等待中任务已取消: execution_id={execution.id}")
                log_operation(request, "execute", "job", f"取消执行: {execution.id}")
                return Response({"message": "已取消执行", "status": ExecutionStatus.CANCELLED})
        elif status_now == ExecutionStatus.RUNNING:
            # RUNNING→CANCELLING：已在执行，进入过渡态，等真实结果回写后收敛
            updated = JobExecution.objects.filter(id=pk, status=ExecutionStatus.RUNNING).update(status=ExecutionStatus.CANCELLING, updated_at=now)
            if updated:
                # 兜底收敛任务：execution.timeout + 缓冲后仍滞留 CANCELLING 则强制收敛为 CANCELLED
                finalize_cancelling_execution.apply_async(args=[execution.id], countdown=execution.timeout + CANCEL_CONVERGE_BUFFER_SECONDS)
                logger.info(f"[cancel] 执行中任务进入取消中: execution_id={execution.id}")
                log_operation(request, "execute", "job", f"取消执行: {execution.id}")
                return Response({"message": "正在取消执行", "status": ExecutionStatus.CANCELLING})

        # CAS 未命中：检查后状态被并发改变，按最新状态拒绝
        return Response(
            {"error": "状态已变更，请刷新后重试"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    @action(detail=True, methods=["post"])
    @HasPermission("job_record-Edit")
    def re_execute(self, request, pk=None):
        """
        重新执行

        基于现有执行记录创建一个新的执行任务，使用相同的参数重新执行。
        """
        original = self.get_object()
        username = request.user.username if request.user else ""
        # BL-NEW-002 / #3403：与 quick_execute 一致，按服务端授权 team 校验原作业归属
        authorized_team_ids = self._get_authorized_team_ids(request)

        try:
            execution = ExecutionService.create_re_execution(original=original, username=username, authorized_team_ids=authorized_team_ids)
        except (ExecutionAuthorizationError, ExecutionDispatchError) as e:
            return Response({"error": e.message}, status=e.status_code)

        return Response(
            JobExecutionDetailSerializer(execution).data,
            status=status.HTTP_201_CREATED,
        )
