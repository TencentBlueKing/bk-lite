"""作业执行编排服务。

将 ``views/execution.py`` 的 quick_execute / file_distribution / re_execute 中
对象校验、危险检测、参数处理、执行记录创建、任务派发整体下沉到此。
View 仅负责鉴权（解析授权 team）、序列化与响应格式化。

为什么用异常而不是返回元组：

- view 内部多个校验串联，元组分支会导致大量 ``if err: return ...`` 噪音；
- 用 :class:`ExecutionAuthorizationError` / :class:`ExecutionDispatchError` 抛出 +
  视图层一次 ``try / except`` 拦截，按异常自带的状态码返回，逻辑更线性。
"""

import json
from typing import List

from apps.job_mgmt.constants import ExecutionStatus, JobType, TargetSource, TriggerSource
from apps.job_mgmt.models import DistributionFile, JobExecution, Playbook, Script, Target
from apps.job_mgmt.services.dangerous_checker import DangerousChecker
from apps.job_mgmt.services.script_params_service import ScriptParamsService
from apps.job_mgmt.utils.team_authz import is_team_authorized

# 快速执行 / 文件分发的默认超时（秒），与序列化器 / 历史行为保持一致
DEFAULT_TIMEOUT = 600
DEFAULT_OVERWRITE_STRATEGY = "overwrite"


class ExecutionAuthorizationError(Exception):
    """业务校验失败的可控异常（view 层映射为 4xx 响应）。

    Args:
        message: 对前端返回的中文文案。
        status_code: 对应的 HTTP 状态码（400 / 403）。
    """

    def __init__(self, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class ExecutionDispatchError(Exception):
    """Celery 派发失败（broker 不可用），view 层映射为 503。

    派发失败时执行记录已由 :func:`dispatch_celery_task` 置为 FAILED，
    避免留下 PENDING 孤立记录。
    """

    def __init__(self, message: str = "任务调度服务暂不可用，请稍后重试"):
        super().__init__(message)
        self.message = message
        self.status_code = 503


class ExecutionService:
    """作业执行业务编排（无状态，纯类方法）。"""

    # ---------------- 目标 / 文件 / 模板对象校验 ---------------- #

    @staticmethod
    def validate_manual_targets(target_list, authorized_team_ids, *, error_label: str = "执行") -> List[Target]:
        """校验 manual 来源的目标存在且属于授权团队。

        Args:
            target_list: 目标条目列表，每项含 ``target_id`` 字段。
            authorized_team_ids: 当前用户授权团队集合，超管传 ``None``。
            error_label: 错误文案动词，如 "执行" / "分发"。
        """
        target_ids = [t.get("target_id") for t in target_list if t.get("target_id")]
        if not target_ids:
            return []
        targets = list(Target.objects.filter(id__in=target_ids))
        if len(targets) != len(set(target_ids)):
            raise ExecutionAuthorizationError("部分目标不存在", status_code=400)
        if any(not is_team_authorized(t.team, authorized_team_ids) for t in targets):
            raise ExecutionAuthorizationError(f"部分目标不属于当前用户的团队，无权{error_label}", status_code=403)
        return targets

    @staticmethod
    def validate_distribution_files(file_ids, authorized_team_ids) -> List[DistributionFile]:
        """校验文件存在且属于授权团队。"""
        distribution_files = list(DistributionFile.objects.filter(id__in=file_ids))
        if len(distribution_files) != len(set(file_ids)):
            raise ExecutionAuthorizationError("部分文件不存在或已过期", status_code=400)
        if any(not is_team_authorized(df.team, authorized_team_ids) for df in distribution_files):
            raise ExecutionAuthorizationError("部分文件不属于当前用户的团队，无权分发", status_code=403)
        return distribution_files

    @staticmethod
    def fetch_authorized_script(script_id, authorized_team_ids) -> Script:
        """按 ID 加载脚本并校验团队归属。"""
        script = Script.objects.filter(id=script_id).first()
        if not script or not is_team_authorized(script.team, authorized_team_ids):
            raise ExecutionAuthorizationError("脚本不存在或无权访问", status_code=403)
        return script

    @staticmethod
    def fetch_authorized_playbook(playbook_id, authorized_team_ids) -> Playbook:
        """按 ID 加载 Playbook 并校验团队归属。"""
        playbook = Playbook.objects.filter(id=playbook_id).first()
        if not playbook or not is_team_authorized(playbook.team, authorized_team_ids):
            raise ExecutionAuthorizationError("Playbook 不存在或无权访问", status_code=403)
        return playbook

    # ---------------- 危险命令 / 路径检测 ---------------- #

    @staticmethod
    def check_dangerous_command(script_content: str, team) -> None:
        check_result = DangerousChecker.check_command(script_content, team)
        if not check_result.can_execute:
            forbidden_rules = [r["rule_name"] for r in check_result.forbidden]
            raise ExecutionAuthorizationError(
                f"脚本包含高危命令，禁止执行: {', '.join(forbidden_rules)}",
                status_code=400,
            )

    @staticmethod
    def check_dangerous_path(target_path: str, team) -> None:
        check_result = DangerousChecker.check_path(target_path, team)
        if not check_result.can_execute:
            forbidden_rules = [r["rule_name"] for r in check_result.forbidden]
            raise ExecutionAuthorizationError(
                f"目标路径为高危路径，禁止分发: {', '.join(forbidden_rules)}",
                status_code=400,
            )

    # ---------------- 文件分发：文件信息构建 ---------------- #

    @staticmethod
    def build_files_info(distribution_files) -> list:
        """从 :class:`DistributionFile` 列表生成 JobExecution.files 用的简化结构。"""
        return [{"name": df.original_name, "file_key": df.file_key} for df in distribution_files]

    # ---------------- 任务派发 ---------------- #

    @staticmethod
    def _dispatch_or_raise(execution: JobExecution) -> None:
        """按 job_type 派发 Celery 任务；broker 不可用时抛 :class:`ExecutionDispatchError`。

        ``tasks`` / ``celery_dispatch`` 采用惰性导入打破
        ``services.__init__ → execution_service → tasks → services.__init__`` 的循环依赖。
        """
        from apps.job_mgmt.services.celery_dispatch import dispatch_celery_task
        from apps.job_mgmt.tasks import distribute_files_task, execute_playbook_task, execute_script_task

        task_map = {
            JobType.SCRIPT: execute_script_task,
            JobType.PLAYBOOK: execute_playbook_task,
            JobType.FILE_DISTRIBUTION: distribute_files_task,
        }
        task_func = task_map.get(execution.job_type)
        if task_func is None or not dispatch_celery_task(task_func, execution):
            raise ExecutionDispatchError()

    # ---------------- 创建 + 派发：三个入口 ---------------- #

    @classmethod
    def create_quick_execution(cls, *, data, team, authorized_team_ids, username, timeout_explicit) -> JobExecution:
        """快速执行：校验对象 → 危险检测 → 创建执行记录 → 派发任务。

        Args:
            data: 已校验的 QuickExecuteSerializer.validated_data。
            team: 已鉴权的本次执行归属 team（list）。
            authorized_team_ids: 当前用户授权团队集合（超管为 None）。
            username: 执行人。
            timeout_explicit: 请求体是否显式传了 timeout（决定是否回退脚本默认超时）。
        """
        target_source = data["target_source"]
        target_list = data["target_list"]
        if target_source == TargetSource.MANUAL:
            cls.validate_manual_targets(target_list, authorized_team_ids, error_label="执行")

        script = cls.fetch_authorized_script(data["script_id"], authorized_team_ids) if data.get("script_id") else None
        playbook = cls.fetch_authorized_playbook(data["playbook_id"], authorized_team_ids) if data.get("playbook_id") else None

        name = data["name"]
        timeout = data.get("timeout", DEFAULT_TIMEOUT)
        if script is not None and not timeout_explicit:
            # 未显式传 timeout 时回退到脚本库定义的超时时间
            timeout = script.timeout
        resolved_params = ScriptParamsService.resolve_params(data.get("params", []), script=script)

        if playbook is not None:
            # Playbook 模式：params 存为 JSON 字符串，保留完整 key-value 关系
            params = json.dumps(ScriptParamsService.params_to_dict(resolved_params), ensure_ascii=False)
            execution = JobExecution.objects.create(
                name=name,
                job_type=JobType.PLAYBOOK,
                status=ExecutionStatus.PENDING,
                playbook=playbook,
                playbook_version=playbook.version,
                params=params,
                timeout=timeout,
                total_count=len(target_list),
                target_source=target_source,
                target_list=target_list,
                team=team,
                executor_user=username,
                created_by=username,
                updated_by=username,
            )
        else:
            # 脚本模式（脚本库 或 临时输入）
            script_content = script.content if script is not None else data.get("script_content", "")
            script_type = script.script_type if script is not None else data.get("script_type", "")
            cls.check_dangerous_command(script_content, team)
            execution = JobExecution.objects.create(
                name=name,
                job_type=JobType.SCRIPT,
                status=ExecutionStatus.PENDING,
                script=script,
                params=ScriptParamsService.params_to_string(resolved_params),
                script_type=script_type,
                script_content=script_content,
                timeout=timeout,
                total_count=len(target_list),
                target_source=target_source,
                target_list=target_list,
                team=team,
                executor_user=username,
                created_by=username,
                updated_by=username,
            )

        cls._dispatch_or_raise(execution)
        return execution

    @classmethod
    def create_file_distribution(cls, *, data, team, authorized_team_ids, username) -> JobExecution:
        """文件分发：校验目标 / 文件 → 危险路径检测 → 创建执行记录 → 派发任务。"""
        target_source = data["target_source"]
        target_list = data["target_list"]
        target_path = data["target_path"]

        if target_source == TargetSource.MANUAL:
            cls.validate_manual_targets(target_list, authorized_team_ids, error_label="分发")
        distribution_files = cls.validate_distribution_files(data["file_ids"], authorized_team_ids)
        cls.check_dangerous_path(target_path, team)

        execution = JobExecution.objects.create(
            name=data["name"],
            job_type=JobType.FILE_DISTRIBUTION,
            status=ExecutionStatus.PENDING,
            files=cls.build_files_info(distribution_files),
            target_path=target_path,
            overwrite_strategy=data.get("overwrite_strategy", DEFAULT_OVERWRITE_STRATEGY),
            timeout=data.get("timeout", DEFAULT_TIMEOUT),
            total_count=len(target_list),
            target_source=target_source,
            target_list=target_list,
            team=team,
            executor_user=username,
            created_by=username,
            updated_by=username,
        )
        cls._dispatch_or_raise(execution)
        return execution

    @classmethod
    def create_re_execution(cls, *, original: JobExecution, username: str, authorized_team_ids) -> JobExecution:
        """重新执行：基于原执行记录创建新执行并派发。

        与 quick_execute / file_distribution 一致，执行前校验调用者对原作业 team
        （及引用的 script / playbook）有权限，消除跨团队水平越权重执行（#3403）。
        ``authorized_team_ids`` 为 ``None`` 表示超管，放行一切。
        """
        # 团队归属校验（须在创建/派发前）
        if not is_team_authorized(original.team, authorized_team_ids):
            raise ExecutionAuthorizationError("无权重新执行该作业", status_code=403)
        if original.script and not is_team_authorized(original.script.team, authorized_team_ids):
            raise ExecutionAuthorizationError("原关联脚本不属于当前用户的团队，无权执行", status_code=403)
        if original.playbook and not is_team_authorized(original.playbook.team, authorized_team_ids):
            raise ExecutionAuthorizationError("原关联 Playbook 不属于当前用户的团队，无权执行", status_code=403)

        target_list = original.target_list or []
        if not target_list:
            raise ExecutionAuthorizationError("原执行目标已不存在", status_code=400)

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
                executor_user=username,
                created_by=username,
                updated_by=username,
            )
        elif original.job_type == JobType.PLAYBOOK:
            if not original.playbook:
                raise ExecutionAuthorizationError("原关联 Playbook 已不存在", status_code=400)
            execution = JobExecution.objects.create(
                name=original.name,
                job_type=JobType.PLAYBOOK,
                trigger_source=TriggerSource.MANUAL,
                status=ExecutionStatus.PENDING,
                playbook=original.playbook,
                playbook_version=original.playbook.version,
                params=original.params,
                timeout=original.timeout,
                total_count=len(target_list),
                target_source=original.target_source,
                target_list=target_list,
                team=original.team,
                executor_user=username,
                created_by=username,
                updated_by=username,
            )
        else:
            # 脚本执行（Playbook 暂不做高危检测，与原实现一致）
            cls.check_dangerous_command(original.script_content, original.team)
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
                executor_user=username,
                created_by=username,
                updated_by=username,
            )

        cls._dispatch_or_raise(execution)
        return execution
