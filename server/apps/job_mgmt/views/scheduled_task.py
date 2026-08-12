"""定时任务视图"""

from django.db import DatabaseError, transaction
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.core.logger import job_logger as logger
from apps.core.utils import viewset_utils
from apps.core.utils.time_util import get_crontab_next_runs
from apps.core.utils.user_group import normalize_user_group_ids
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
from apps.job_mgmt.services.celery_dispatch import dispatch_celery_task
from apps.job_mgmt.services.dangerous_checker import DangerousChecker
from apps.job_mgmt.services.scheduled_task_authz import (
    ScheduledTaskTeamBoundaryError,
    validate_scheduled_task_resource_boundary,
)
from apps.job_mgmt.services.scheduled_task_service import ScheduledTaskService
from apps.job_mgmt.services.script_params_service import ScriptParamsService
from apps.job_mgmt.tasks import distribute_files_task, execute_playbook_task, execute_script_task
from apps.job_mgmt.utils.team_authz import is_team_authorized, normalize_authorized_team_ids
from apps.system_mgmt.utils.operation_log_utils import log_operation


class ScheduledTaskViewSet(AuthViewSet):
    """定时任务视图集"""

    queryset = ScheduledTask.objects.all()
    serializer_class = ScheduledTaskListSerializer
    filterset_class = ScheduledTaskFilter
    search_fields = ["name", "description"]
    ORGANIZATION_FIELD = "team"
    permission_key = "job"

    @staticmethod
    def _validate_resource_boundary(attrs, *, instance=None, lock_resources=False):
        try:
            validate_scheduled_task_resource_boundary(
                attrs,
                instance=instance,
                lock_resources=lock_resources,
            )
        except ScheduledTaskTeamBoundaryError as exc:
            raise serializers.ValidationError({exc.field: exc.message}) from exc

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

        with transaction.atomic():
            # 校验用户是否有目标组织的权限，并锁定全部稳定资源直至任务落库。
            team = serializer.validated_data.get("team", [])
            self._validate_org_field_permission(request, team)
            self._validate_resource_boundary(serializer.validated_data, lock_resources=True)
            instance = serializer.save()
        log_operation(request, "create", "job", f"新增定时任务: {instance.name}")
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

        with transaction.atomic():
            instance = ScheduledTask.objects.select_for_update().get(pk=instance.pk)
            serializer.instance = instance
            disable_only = serializer.validated_data.get("is_enabled") is False and set(serializer.validated_data) == {
                "is_enabled"
            }
            if disable_only:
                # 存量任务可能含当前用户已不再拥有的旧团队；纯禁用必须始终可止损。
                if not request.user.is_superuser and not is_team_authorized(
                    instance.team,
                    normalize_authorized_team_ids(getattr(request.user, "group_list", [])),
                ):
                    raise PermissionDenied("无权禁用其他团队的定时任务")
                instance.is_enabled = False
                instance.updated_by = request.user.username if request.user else ""
                instance.save(update_fields=["is_enabled", "updated_by", "updated_at"])
                try:
                    with transaction.atomic():
                        ScheduledTaskService.toggle_periodic_task_or_raise(instance.id, False)
                except DatabaseError as exc:
                    # 内层 savepoint 隔离 Beat 写失败，业务禁用仍可提交；残留触发会在 worker 中重试同步。
                    logger.exception(f"纯禁用定时任务时同步 Beat 失败，将由残留触发重试: scheduled_task_id={instance.id}, error={exc}")
            else:
                # 校验用户是否有目标组织的权限
                team = serializer.validated_data.get("team", instance.team)
                self._validate_org_field_permission(request, team)
                self._validate_resource_boundary(
                    serializer.validated_data,
                    instance=instance,
                    lock_resources=True,
                )
                instance = serializer.save()
        log_operation(request, "update", "job", f"编辑定时任务: {instance.name}")
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

        schedule_sync_pending = False
        with transaction.atomic():
            instance = ScheduledTask.objects.select_for_update().get(pk=instance.pk)
            is_enabled = serializer.validated_data["is_enabled"]
            if is_enabled:
                self._validate_resource_boundary({}, instance=instance, lock_resources=True)

            instance.is_enabled = is_enabled
            instance.updated_by = request.user.username if request.user else ""
            instance.save(update_fields=["is_enabled", "updated_by", "updated_at"])

            try:
                with transaction.atomic():
                    schedule_synced = ScheduledTaskService.toggle_periodic_task_or_raise(instance.id, instance.is_enabled)
            except DatabaseError:
                if instance.is_enabled:
                    raise serializers.ValidationError({"is_enabled": "同步定时调度状态失败，请稍后重试"})
                schedule_synced = False
            if not schedule_synced and instance.is_enabled:
                raise serializers.ValidationError({"is_enabled": "同步定时调度状态失败，请稍后重试"})
            schedule_sync_pending = not schedule_synced
        log_operation(request, "execute", "job", f"切换定时任务状态: {instance.name}")

        return Response(
            {
                "message": (
                    f"任务已{'启用' if instance.is_enabled else '禁用'}"
                    + ("，调度状态将在下次触发时重试同步" if schedule_sync_pending else "")
                ),
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
        with transaction.atomic():
            instance = ScheduledTask.objects.select_for_update().get(pk=instance.pk)
            self._validate_resource_boundary({}, instance=instance, lock_resources=True)

            # 获取执行目标
            target_list = instance.target_list or []
            if not target_list:
                return Response({"error": "没有配置执行目标"}, status=status.HTTP_400_BAD_REQUEST)

            # 处理参数：解析 is_modified=False 的参数并转换为字符串
            params = instance.params if isinstance(instance.params, list) else []
            resolved_params = ScriptParamsService.resolve_params(params, script=instance.script)
            params_str = ScriptParamsService.params_to_string(resolved_params)

            # 脚本内容：优先从关联的 Script 对象获取，回退到定时任务上的临时输入字段
            script_content = instance.script_content or ""
            script_type = instance.script_type or ""
            if instance.script:
                script_content = instance.script.content or script_content
                script_type = instance.script.script_type or script_type

            # 高危命令/路径预检：与 execute_scheduled_task 保持一致，命中则直接拒绝，不创建执行记录
            team = instance.team or []
            if instance.job_type == JobType.SCRIPT and script_content:
                check_result = DangerousChecker.check_command(script_content, team)
                if not check_result.can_execute:
                    forbidden_rules = [r["rule_name"] for r in check_result.forbidden]
                    return Response(
                        {"error": f"脚本包含高危命令，已拦截: {', '.join(forbidden_rules)}"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            if instance.job_type == JobType.FILE_DISTRIBUTION and instance.target_path:
                check_result = DangerousChecker.check_path(instance.target_path, team)
                if not check_result.can_execute:
                    forbidden_rules = [r["rule_name"] for r in check_result.forbidden]
                    return Response(
                        {"error": f"目标路径为高危路径，已拦截: {', '.join(forbidden_rules)}"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            # 资源锁与任务行锁持有到执行快照落库，关闭校验后的 TOCTOU 窗口。
            execution = JobExecution.objects.create(
                name=f"[手动触发] {instance.name}",
                job_type=instance.job_type,
                status=ExecutionStatus.PENDING,
                scheduled_task=instance,
                enforce_scheduled_team_boundary=True,
                script=instance.script,
                playbook=instance.playbook,
                playbook_version=instance.playbook.version if instance.playbook else "",
                params=params_str,
                script_type=script_type,
                script_content=script_content,
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

        # 触发异步任务；broker 不可用时置 FAILED 并返回 503
        task_func_map = {
            JobType.SCRIPT: execute_script_task,
            JobType.FILE_DISTRIBUTION: distribute_files_task,
            JobType.PLAYBOOK: execute_playbook_task,
        }
        task_func = task_func_map.get(instance.job_type)
        if task_func and not dispatch_celery_task(task_func, execution):
            return Response(
                {"error": "任务调度服务暂不可用，请稍后重试"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        log_operation(request, "execute", "job", f"立即执行定时任务: {instance.name}")

        return Response(
            {
                "message": "已触发执行",
                "execution_id": execution.id,
            }
        )

    def _get_delete_queryset(self, request, ids):
        tasks = self.filter_queryset(self.get_queryset()).filter(id__in=ids)
        if request.user.is_superuser:
            return tasks

        current_team = self._validate_current_team_permission(request)
        include_children = request.COOKIES.get("include_children", "0") == "1"
        scope_team_ids = {current_team}
        if include_children:
            subtree_ids = self.extract_child_group_ids(getattr(request.user, "group_tree", []), current_team)
            if subtree_ids:
                scope_team_ids = set(normalize_user_group_ids(subtree_ids))

        scope_query = viewset_utils.build_json_membership_query(tasks, self.ORGANIZATION_FIELD, scope_team_ids)
        tasks = tasks.filter(scope_query)
        if not tasks.exists():
            return tasks

        permission_rules = viewset_utils.get_permission_rules(
            request.user,
            current_team,
            self._get_app_name(),
            self.permission_key,
            include_children,
        )
        if not isinstance(permission_rules, dict):
            return tasks.none()

        permission_teams = permission_rules.get("team", [])
        permission_team_ids = set(normalize_user_group_ids(permission_teams if isinstance(permission_teams, list) else []))
        if include_children and current_team in permission_team_ids:
            granted_team_ids = scope_team_ids
        else:
            granted_team_ids = permission_team_ids & scope_team_ids

        operate_instance_ids = set()
        instance_rules = permission_rules.get("instance", [])
        for rule in instance_rules if isinstance(instance_rules, list) else []:
            if not isinstance(rule, dict) or "Operate" not in rule.get("permission", []):
                continue
            try:
                operate_instance_ids.add(int(rule["id"]))
            except (KeyError, TypeError, ValueError):
                continue

        authorized_ids = []
        for task in tasks:
            task_team_ids = set(normalize_user_group_ids(task.team))
            if not task_team_ids & scope_team_ids:
                continue
            if task_team_ids & granted_team_ids or task.id in operate_instance_ids:
                authorized_ids.append(task.id)
        return tasks.filter(id__in=authorized_ids)

    @HasPermission("cron_task-Delete")
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if not self._get_delete_queryset(request, [instance.id]).exists():
            message = self.loader.get("error.no_permission_delete") if self.loader else "User does not have permission to delete this instance"
            return self.value_error(message)

        # 删除关联的 celery-beat PeriodicTask
        ScheduledTaskService.delete_periodic_task(instance.id)

        instance.delete()
        log_operation(request, "delete", "job", f"删除定时任务: {instance.name}")
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
        tasks = self._get_delete_queryset(request, ids)

        # 删除关联的 PeriodicTask
        for task in tasks:
            ScheduledTaskService.delete_periodic_task(task.id)

        deleted_count, _ = tasks.delete()
        log_operation(request, "delete", "job", f"批量删除定时任务: (共{deleted_count}个)")

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
