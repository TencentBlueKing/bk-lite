"""Job Management NATS API - 用于数据权限规则"""

from celery import current_app
from django.db import connection, transaction
from django.utils import timezone

import nats_client
from apps.core.logger import job_logger as logger
from apps.core.utils.ssrf_validator import SSRFError, SSRFValidator
from apps.job_mgmt.constants import CallbackType, ExecutionStatus, JobType, TriggerSource
from apps.job_mgmt.models import DangerousPath, DangerousRule, DistributionFile, JobExecution, Playbook, ScheduledTask, Script, Target
from apps.job_mgmt.services.callback_service import send_callback
from apps.job_mgmt.services.celery_dispatch import dispatch_celery_task
from apps.job_mgmt.services.completion_outbox_service import enqueue_terminal_effects
from apps.job_mgmt.services.dangerous_checker import DangerousChecker
from apps.job_mgmt.services.script_normalize import normalize_script_line_endings
from apps.job_mgmt.services.script_params_service import ScriptParamsService
from apps.job_mgmt.tasks import distribute_files_task, execute_script_task, finalize_cancelling_execution
from apps.job_mgmt.utils.team_authz import is_team_authorized, normalize_team
from apps.rpc.sensitive import sanitize_sensitive_data, summarize_ansible_callback

CANCEL_CONVERGE_BUFFER_SECONDS = 60


def _validate_callback_config(callback_type: str, callback_url: str, callback_subject: str, tag: str):
    """校验回调配置，返回错误信息字符串；通过则返回 None。

    - callback_type 必须为 web/nats/both
    - web 通道（web/both）：对 callback_url 做 SSRF 校验（宽松模式，仅阻断云元数据）
    - nats 通道（nats/both）：callback_subject 必填
    """
    if callback_type not in (CallbackType.WEB, CallbackType.NATS, CallbackType.BOTH):
        return f"callback_type 必须为 web/nats/both，收到: {callback_type}"

    if CallbackType.use_web(callback_type) and callback_url:
        try:
            SSRFValidator.validate_callback(callback_url)
        except SSRFError as e:
            logger.warning(f"[{tag}] callback_url SSRF 校验失败: url={callback_url}, error={e}")
            return f"Invalid callback_url: {e}"

    if CallbackType.use_nats(callback_type) and not callback_subject:
        return "callback_type 含 nats 时 callback_subject 不能为空"

    return None


@nats_client.register
def get_job_mgmt_module_list():
    """获取作业管理模块列表"""
    return [
        {"name": "script", "display_name": "脚本库"},
        {"name": "playbook", "display_name": "Playbook库"},
        {"name": "target", "display_name": "目标"},
        {"name": "job_execution", "display_name": "作业执行"},
        {"name": "scheduled_task", "display_name": "定时任务"},
        {
            "name": "system",
            "display_name": "系统管理",
            "children": [
                {"name": "dangerous_rule", "display_name": "高危命令"},
                {"name": "dangerous_path", "display_name": "高危路径"},
            ],
        },
    ]


@nats_client.register
def get_job_mgmt_module_data(module, child_module, page, page_size, group_id, *, team=None):
    """获取作业管理模块数据"""
    model_map = {
        "script": Script,
        "playbook": Playbook,
        "target": Target,
        "job_execution": JobExecution,
        "scheduled_task": ScheduledTask,
    }
    system_model_map = {
        "dangerous_rule": DangerousRule,
        "dangerous_path": DangerousPath,
    }

    if module != "system":
        model = model_map.get(module)
        if model is None:
            return {"result": False, "message": f"未知 module: {module}"}
    else:
        model = system_model_map.get(child_module)
        if model is None:
            return {"result": False, "message": f"未知 child_module: {child_module}"}

    requested_teams = normalize_team(group_id)
    if len(requested_teams) != 1:
        return {"result": False, "message": "group_id 参数非法"}

    authorized_team_ids = normalize_team(team)
    if not authorized_team_ids:
        return {"result": False, "message": "team 不能为空"}

    group_id = next(iter(requested_teams))
    if not is_team_authorized(group_id, authorized_team_ids):
        return {"result": False, "message": "无权访问该团队数据"}

    try:
        page = max(1, int(page))
        page_size = max(1, int(page_size))
    except (TypeError, ValueError):
        return {"result": False, "message": "page/page_size 参数非法"}

    queryset = _filter_module_data_by_team(model.objects.all(), group_id)

    # 计算总数
    total_count = queryset.count()

    # 计算分页
    start = (page - 1) * page_size
    end = page * page_size

    # 获取当前页的数据
    data_list = queryset.values("id", "name")[start:end]

    return {
        "count": total_count,
        "items": list(data_list),
    }


def _filter_module_data_by_team(queryset, group_id):
    if connection.features.supports_json_field_contains:
        return queryset.filter(team__contains=group_id)

    matched_ids = [item.id for item in queryset.only("id", "team") if group_id in normalize_team(getattr(item, "team", None))]
    return queryset.filter(id__in=matched_ids)


@nats_client.register
def job_script_detail(data: dict):
    """返回单个脚本模板的完整详情（content/script_type/params/timeout）。

    供第三方 App（如告警动作）按 id 读取脚本内容以内联执行。
    Args:
        data: {"id": <script_id>}
    Returns:
        {"result": True, "data": {id, name, script_type, content, params, timeout}} 或 {"result": False, "message": "..."}
    """
    script_id = data.get("id")
    authorized_team_ids = normalize_team(data.get("team"))
    if not authorized_team_ids:
        return {"result": False, "message": "team 不能为空"}
    script = Script.objects.filter(id=script_id).first()
    if not script or not (normalize_team(script.team) & authorized_team_ids):
        return {"result": False, "message": f"脚本不存在: id={script_id}"}
    return {
        "result": True,
        "data": {
            "id": script.id,
            "name": script.name,
            "script_type": script.script_type,
            "content": script.content,
            "params": script.params,
            "timeout": script.timeout,
        },
    }


def _failure_results(execution, error_message: str, finished_at) -> list[dict]:
    safe_error = str(sanitize_sensitive_data(error_message))
    return [
        {
            "target_key": str(target.get("target_id", "")),
            "name": target.get("name", ""),
            "ip": target.get("ip", ""),
            "status": ExecutionStatus.FAILED,
            "stdout": "",
            "stderr": safe_error,
            "exit_code": 1,
            "error_message": safe_error,
            "started_at": execution.started_at.isoformat() if execution.started_at else "",
            "finished_at": finished_at.isoformat(),
        }
        for target in execution.target_list or []
    ]


def _target_map(target_list: list[dict]) -> dict[str, dict]:
    result = {}
    for target in target_list:
        result[str(target.get("ip", ""))] = target
        result[str(target.get("target_id", ""))] = target
    return result


def _host_execution_result(execution, target, host_result, finished_at: str) -> dict:
    host_key = str(host_result.get("host", ""))
    host_status = host_result.get("status")
    return {
        "target_key": str(target.get("target_id", "")),
        "name": target.get("name", host_key),
        "ip": target.get("ip", host_key),
        "status": ExecutionStatus.SUCCESS if host_status == "success" else ExecutionStatus.FAILED,
        "stdout": str(sanitize_sensitive_data(str(host_result.get("stdout", "")))),
        "stderr": str(sanitize_sensitive_data(str(host_result.get("stderr", "")))),
        "exit_code": host_result.get("exit_code", 0),
        "error_message": str(sanitize_sensitive_data(str(host_result.get("error_message", "")))),
        "started_at": execution.started_at.isoformat() if execution.started_at else "",
        "finished_at": finished_at,
    }


def _missing_execution_result(execution, target, error_output: str, finished_at: str) -> dict:
    message = error_output or "未收到该目标执行结果"
    return {
        "target_key": str(target.get("target_id", "")),
        "name": target.get("name", ""),
        "ip": target.get("ip", ""),
        "status": ExecutionStatus.FAILED,
        "stdout": "",
        "stderr": message,
        "exit_code": 1,
        "error_message": message,
        "started_at": execution.started_at.isoformat() if execution.started_at else "",
        "finished_at": finished_at,
    }


def _normalize_ansible_results(execution, data: dict, finished_at) -> tuple[list[dict], str]:
    raw_result = data.get("result", [])
    if not (isinstance(raw_result, list) and raw_result and all(isinstance(item, dict) for item in raw_result)):
        error = f"回调结果格式非法: {sanitize_sensitive_data(raw_result)}"
        return _failure_results(execution, error, finished_at), "非法的新版本结果格式"

    target_list = execution.target_list or []
    targets_by_key = _target_map(target_list)
    seen_target_keys = set()
    results = []
    callback_finished_at = data.get("finished_at") or finished_at.isoformat()

    for host_result in raw_result:
        host_key = str(host_result.get("host", ""))
        target = targets_by_key.get(host_key)
        if not target:
            error = f"结果中的主机未匹配到目标: {host_key}"
            return _failure_results(execution, error, finished_at), error
        target_key = str(target.get("target_id", ""))
        if target_key in seen_target_keys:
            error = f"结果中的主机重复: {host_key}"
            return _failure_results(execution, error, finished_at), error
        seen_target_keys.add(target_key)
        results.append(_host_execution_result(execution, target, host_result, callback_finished_at))

    error_output = str(sanitize_sensitive_data(data.get("error", "")))
    for target in target_list:
        target_key = str(target.get("target_id", ""))
        if target_key not in seen_target_keys:
            results.append(_missing_execution_result(execution, target, error_output, callback_finished_at))
    return results, ""


def _write_ansible_terminal(execution, data: dict, *, reconcile_cancel_timeout: bool = False):
    finished_at = timezone.now()
    results, validation_error = _normalize_ansible_results(execution, data, finished_at)
    was_cancelling = execution.status == ExecutionStatus.CANCELLING or reconcile_cancel_timeout
    if was_cancelling:
        final_status = ExecutionStatus.CANCELLED
    elif validation_error or any(item["status"] == ExecutionStatus.FAILED for item in results):
        final_status = ExecutionStatus.FAILED
    else:
        final_status = ExecutionStatus.SUCCESS

    execution.status = final_status
    execution.execution_results = results
    execution.finished_at = finished_at
    execution.success_count = sum(1 for item in results if item["status"] == ExecutionStatus.SUCCESS)
    execution.failed_count = sum(1 for item in results if item["status"] == ExecutionStatus.FAILED)
    execution.terminal_source = JobExecution.TerminalSource.ANSIBLE_CALLBACK
    execution.save(
        update_fields=[
            "status",
            "terminal_source",
            "execution_results",
            "finished_at",
            "success_count",
            "failed_count",
            "updated_at",
        ]
    )
    enqueue_terminal_effects(execution, refresh_undelivered=reconcile_cancel_timeout)
    return validation_error


@nats_client.register
def ansible_task_callback(data: dict):
    """持久化首个 Ansible 终态回调及其可恢复副作用。"""
    logger.info("[ansible_task_callback] %s", summarize_ansible_callback(data))
    task_id = data.get("task_id")
    if not task_id:
        logger.warning("[ansible_task_callback] 缺少 task_id")
        return {"success": False, "message": "缺少 task_id"}

    with transaction.atomic():
        execution = JobExecution.objects.select_for_update().filter(id=task_id).first()
        if execution is None:
            logger.warning("[ansible_task_callback] 执行记录不存在: task_id=%s", task_id)
            return {"success": False, "message": f"执行记录不存在: {task_id}"}
        reconcile_cancel_timeout = (
            execution.status == ExecutionStatus.CANCELLED
            and execution.terminal_source == JobExecution.TerminalSource.CANCEL_TIMEOUT
        )
        if execution.status in ExecutionStatus.TERMINAL_STATES and not reconcile_cancel_timeout:
            logger.info(
                "[ansible_task_callback] 任务已处于终态: task_id=%s, status=%s",
                task_id,
                execution.status,
            )
            return {"success": True, "message": "任务已处理"}
        validation_error = _write_ansible_terminal(
            execution,
            data,
            reconcile_cancel_timeout=reconcile_cancel_timeout,
        )
        final_status = execution.status

    if validation_error:
        logger.warning(
            "[ansible_task_callback] 任务异常结果已写入终态: task_id=%s, status=%s, reason=%s",
            task_id,
            final_status,
            validation_error,
        )
        return {"success": False, "message": f"{validation_error}，已收敛到 {final_status.upper()}"}

    logger.info("[ansible_task_callback] 任务完成: task_id=%s, status=%s", task_id, final_status)
    return {"success": True, "message": "回调处理成功"}


# ============================================================
# 开放接口：供第三方 App（如补丁管理）通过 NATS 调用
# ============================================================


@nats_client.register
def job_script_execute(data: dict):
    """
    脚本执行（NATS 开放接口）

    Args:
        data: 请求数据，包含：
            - name: 作业名称（必填）
            - target_source: 目标来源 node_mgmt|manual（必填）
            - target_list: 目标列表（必填）
            - script_type: 脚本类型 shell|python|powershell|bat（必填）
            - script_content: 脚本内容（必填）
            - params: 参数列表（可选）
            - timeout: 超时秒数（可选，默认600）
            - team: 团队ID列表（必填）
            - callback_type: 回调通道 web|nats|both（可选，默认 web）
            - callback_url: web 通道回调地址（callback_type 含 web 时使用）
            - callback_subject: nats 通道回调主题，如 bklite.alert_job_result（callback_type 含 nats 时必填）

    Returns:
        {"result": True, "data": {"task_id": <int>}} 或 {"result": False, "message": "..."}
    """

    # 参数校验
    name = data.get("name")
    target_source = data.get("target_source")
    target_list = data.get("target_list")
    script_type = data.get("script_type")
    script_content = data.get("script_content")
    team = data.get("team", [])
    timeout = data.get("timeout", 600)
    params = data.get("params", [])
    callback_type = data.get("callback_type", CallbackType.WEB)
    callback_url = data.get("callback_url")
    callback_subject = data.get("callback_subject")

    if not name:
        return {"result": False, "message": "name 不能为空"}
    if target_source not in ("node_mgmt", "manual"):
        return {"result": False, "message": "target_source 必须为 node_mgmt 或 manual"}
    if not target_list:
        return {"result": False, "message": "目标列表不能为空"}
    if script_type not in ("shell", "python", "powershell", "bat"):
        return {"result": False, "message": "script_type 必须为 shell/python/powershell/bat"}
    if not script_content:
        return {"result": False, "message": "script_content 不能为空"}
    if not team:
        return {"result": False, "message": "team 不能为空"}

    # 回调配置校验（web 通道 SSRF 校验、nats 通道 subject 必填）
    cb_err = _validate_callback_config(callback_type, callback_url, callback_subject, "job_script_execute")
    if cb_err:
        return {"result": False, "message": cb_err}

    # 高危命令检测
    check_result = DangerousChecker.check_command(script_content, team)
    if not check_result.can_execute:
        forbidden_rules = [r["rule_name"] for r in check_result.forbidden]
        return {"result": False, "message": f"脚本包含高危命令，禁止执行: {', '.join(forbidden_rules)}"}

    # 构建 params 字符串
    params_str = ScriptParamsService.params_to_string(params) if params else ""

    # 入库前规范化换行符（CRLF/CR → LF；bat/powershell 保留原样）。
    # NATS 入口绕过 REST serializer, 必须独立处理; worker 兜底仍保留。
    script_content = normalize_script_line_endings(script_content, script_type)

    # 创建执行记录

    execution = JobExecution.objects.create(
        name=name,
        job_type=JobType.SCRIPT,
        trigger_source=TriggerSource.API,
        status=ExecutionStatus.PENDING,
        script_type=script_type,
        script_content=script_content,
        params=params_str,
        timeout=timeout,
        total_count=len(target_list),
        target_source=target_source,
        target_list=target_list,
        team=team,
        callback_type=callback_type,
        callback_url=callback_url,
        callback_subject=callback_subject,
        created_by="api",
        updated_by="api",
    )

    # 触发异步执行（Celery Worker）
    if not dispatch_celery_task(execute_script_task, execution):
        return {"result": False, "message": "任务调度服务暂不可用，请稍后重试"}

    return {"result": True, "data": {"task_id": execution.id}}


@nats_client.register
def job_file_distribute(data: dict):
    """
    文件分发（NATS 开放接口）

    Args:
        data: 请求数据，包含：
            - name: 作业名称（必填）
            - file_keys: 已上传文件的 file_key 列表（必填）
            - target_source: 目标来源（必填）
            - target_list: 目标列表（必填）
            - target_path: 目标路径（必填）
            - overwrite_strategy: 覆盖策略（可选，默认overwrite）
            - timeout: 超时秒数（可选，默认600）
            - team: 团队ID列表（必填）
            - callback_type: 回调通道 web|nats|both（可选，默认 web）
            - callback_url: web 通道回调地址（callback_type 含 web 时使用）
            - callback_subject: nats 通道回调主题，如 bklite.alert_job_result（callback_type 含 nats 时必填）

    Returns:
        {"result": True, "data": {"task_id": <int>}} 或 {"result": False, "message": "..."}
    """

    name = data.get("name")
    file_keys = data.get("file_keys", [])
    target_source = data.get("target_source")
    target_list = data.get("target_list")
    target_path = data.get("target_path")
    overwrite_strategy = data.get("overwrite_strategy", "overwrite")
    timeout = data.get("timeout", 600)
    team = data.get("team", [])
    authorized_team_ids = normalize_team(team)
    callback_type = data.get("callback_type", CallbackType.WEB)
    callback_url = data.get("callback_url")
    callback_subject = data.get("callback_subject")

    if not name:
        return {"result": False, "message": "name 不能为空"}
    if not file_keys:
        return {"result": False, "message": "file_keys 不能为空"}
    if target_source not in ("node_mgmt", "manual"):
        return {"result": False, "message": "target_source 必须为 node_mgmt 或 manual"}
    if not target_list:
        return {"result": False, "message": "目标列表不能为空"}
    if not target_path:
        return {"result": False, "message": "target_path 不能为空"}
    if not authorized_team_ids:
        return {"result": False, "message": "team 不能为空或格式非法"}

    # 回调配置校验（web 通道 SSRF 校验、nats 通道 subject 必填）
    cb_err = _validate_callback_config(callback_type, callback_url, callback_subject, "job_file_distribute")
    if cb_err:
        return {"result": False, "message": cb_err}

    # 高危路径检测
    check_result = DangerousChecker.check_path(target_path, team)
    if not check_result.can_execute:
        forbidden_rules = [r["rule_name"] for r in check_result.forbidden]
        return {"result": False, "message": f"目标路径为高危路径，禁止分发: {', '.join(forbidden_rules)}"}

    # 文件必须属于本次作业声明的团队。将团队范围直接落到 ORM 查询，
    # 对跨团队文件与历史无归属文件统一 fail-closed，避免泄露其存在性。
    distribution_files = list(DistributionFile.objects.filter(file_key__in=file_keys, team__in=authorized_team_ids))
    found_keys = {df.file_key for df in distribution_files}
    missing_keys = [k for k in file_keys if k not in found_keys]
    if missing_keys:
        return {"result": False, "message": f"部分文件不存在、已过期或无权访问: {', '.join(missing_keys)}"}

    # 构建文件信息
    files_info = [{"name": df.original_name, "file_key": df.file_key} for df in distribution_files]

    # 创建执行记录
    execution = JobExecution.objects.create(
        name=name,
        job_type=JobType.FILE_DISTRIBUTION,
        trigger_source=TriggerSource.API,
        status=ExecutionStatus.PENDING,
        files=files_info,
        target_path=target_path,
        overwrite_strategy=overwrite_strategy,
        timeout=timeout,
        total_count=len(target_list),
        target_source=target_source,
        target_list=target_list,
        team=team,
        callback_type=callback_type,
        callback_url=callback_url,
        callback_subject=callback_subject,
        created_by="api",
        updated_by="api",
    )

    # 触发异步执行（Celery Worker）
    if not dispatch_celery_task(distribute_files_task, execution):
        return {"result": False, "message": "任务调度服务暂不可用，请稍后重试"}

    return {"result": True, "data": {"task_id": execution.id}}


@nats_client.register
def job_status_batch_query(data: dict):
    """
    批量查询作业状态（NATS 开放接口）

    Args:
        data: {"task_ids": [1, 2, 3]}

    Returns:
        {"result": True, "data": [{"task_id": 1, "status": "success", ...}, ...]}
    """
    task_ids = data.get("task_ids", [])
    if not task_ids:
        return {"result": False, "message": "task_ids 不能为空"}

    executions = JobExecution.objects.filter(id__in=task_ids)
    execution_map = {e.id: e for e in executions}

    results = []
    for task_id in task_ids:
        execution = execution_map.get(task_id)
        if execution:
            results.append(
                {
                    "task_id": execution.id,
                    "status": execution.status,
                    "total_count": execution.total_count,
                    "success_count": execution.success_count,
                    "failed_count": execution.failed_count,
                }
            )
        else:
            results.append({"task_id": task_id, "status": "not_found"})

    return {"result": True, "data": results}


def _build_job_detail_payload(execution, *, include_sensitive: bool):
    payload = {
        "task_id": execution.id,
        "name": execution.name,
        "job_type": execution.job_type,
        "status": execution.status,
        "timeout": execution.timeout,
        "started_at": execution.started_at.isoformat() if execution.started_at else None,
        "finished_at": execution.finished_at.isoformat() if execution.finished_at else None,
        "total_count": execution.total_count,
        "success_count": execution.success_count,
        "failed_count": execution.failed_count,
    }
    if not include_sensitive:
        payload.update({"detail_limited": True, "requires_team": True})
        return payload
    payload.update(
        {
            "detail_limited": False,
            "requires_team": False,
            "script_type": execution.script_type,
            "script_content": execution.script_content,
            "target_list": execution.target_list,
            "execution_results": execution.execution_results,
        }
    )
    return payload


@nats_client.register
def job_detail_query(data: dict):
    """
    查询单个作业详情（NATS 开放接口）

    Args:
        data: {"task_id": 123, "team": [1]}。兼容旧调用 {"task_id": 123}，
              但旧调用只返回不含脚本明文/执行结果的安全元数据。

    Returns:
        {"result": True, "data": {...}} 或 {"result": False, "message": "..."}
    """
    task_id = data.get("task_id")
    team = normalize_team(data.get("team", []))
    if not task_id:
        return {"result": False, "message": "task_id 不能为空"}

    try:
        execution = JobExecution.objects.get(id=task_id)
    except JobExecution.DoesNotExist:
        return {"result": False, "message": "任务不存在"}

    if not team:
        return {"result": True, "data": _build_job_detail_payload(execution, include_sensitive=False)}

    if not is_team_authorized(execution.team, team):
        return {"result": False, "message": "无权查询该任务"}

    return {"result": True, "data": _build_job_detail_payload(execution, include_sensitive=True)}


@nats_client.register
def job_task_terminate(data=None, task_id=None, **kwargs):
    if isinstance(data, dict):
        task_id = data.get("task_id", task_id)
        caller_team = data.get("caller_team", kwargs.get("caller_team", []))
    else:
        caller_team = kwargs.get("caller_team", [])
    if task_id is None:
        task_id = kwargs.get("task_id")
    if not task_id:
        return {"result": False, "message": "task_id 不能为空"}
    if not caller_team:
        return {"result": False, "message": "caller_team 不能为空"}

    try:
        execution = JobExecution.objects.get(id=task_id)
    except JobExecution.DoesNotExist:
        return {"result": False, "message": "任务不存在"}

    # 归属校验：执行记录所属团队必须与调用方团队有交集
    if not set(execution.team) & set(caller_team):
        logger.warning(
            "[job_task_terminate] 团队归属校验失败: task_id=%s, execution.team=%s, caller_team=%s",
            task_id,
            execution.team,
            caller_team,
        )
        return {"result": False, "message": "无权取消该任务"}

    status_now = execution.status
    if status_now in ExecutionStatus.TERMINAL_STATES:
        return {"result": False, "message": f"任务已处于终态({execution.get_status_display()})，无法取消"}
    if status_now == ExecutionStatus.CANCELLING:
        return {"result": False, "message": "任务正在取消中，请勿重复操作"}

    if execution.celery_task_id:
        try:
            current_app.control.revoke(execution.celery_task_id)
            logger.info("[job_task_terminate] 已 revoke Celery 任务: execution_id=%s, task_id=%s", execution.id, execution.celery_task_id)
        except Exception as error:
            logger.warning("[job_task_terminate] revoke Celery 任务失败: execution_id=%s, error=%s", execution.id, error)

    now = timezone.now()
    if status_now == ExecutionStatus.PENDING:
        updated = JobExecution.objects.filter(id=task_id, status=ExecutionStatus.PENDING).update(
            status=ExecutionStatus.CANCELLED,
            finished_at=now,
            updated_at=now,
        )
        if updated:
            execution.refresh_from_db()
            send_callback(execution)
            return {
                "result": True,
                "data": {"task_id": execution.id, "status": ExecutionStatus.CANCELLED, "message": "已取消执行"},
            }

    if status_now == ExecutionStatus.RUNNING:
        updated = JobExecution.objects.filter(id=task_id, status=ExecutionStatus.RUNNING).update(
            status=ExecutionStatus.CANCELLING,
            updated_at=now,
        )
        if updated:
            finalize_cancelling_execution.apply_async(
                args=[execution.id],
                countdown=execution.timeout + CANCEL_CONVERGE_BUFFER_SECONDS,
            )
            execution.refresh_from_db()
            send_callback(execution)
            return {
                "result": True,
                "data": {"task_id": execution.id, "status": ExecutionStatus.CANCELLING, "message": "正在取消执行"},
            }

    return {"result": False, "message": "状态已变更，请刷新后重试"}


@nats_client.register
def job_target_list(data: dict):
    """
    查询目标列表（NATS 开放接口）

    供第三方 App 获取可用目标，用于构建 target_list 参数。

    Args:
        data: 请求数据，包含：
            - name: 按名称模糊搜索（可选）
            - ip: 按IP模糊搜索（可选）
            - os_type: 按系统类型过滤 linux|windows（可选）
            - page: 页码（可选，默认1）
            - page_size: 每页数量（可选，默认20，传 -1 返回全部）

    Returns:
        {"result": True, "data": {"count": N, "items": [...]}}
    """
    name = data.get("name")
    ip = data.get("ip")
    os_type = data.get("os_type")
    page = data.get("page", 1)
    page_size = data.get("page_size", 20)

    queryset = Target.objects.all()

    if name:
        queryset = queryset.filter(name__icontains=name)
    if ip:
        queryset = queryset.filter(ip__icontains=ip)
    if os_type:
        queryset = queryset.filter(os_type=os_type)

    total_count = queryset.count()

    if page_size == -1:
        targets = queryset.order_by("-id")
    else:
        start = (page - 1) * page_size
        end = start + page_size
        targets = queryset.order_by("-id")[start:end]

    items = []
    for t in targets:
        items.append(
            {
                "target_id": t.id,
                "name": t.name,
                "ip": str(t.ip),
                "os_type": t.os_type,
                "cloud_region_id": t.cloud_region_id,
            }
        )

    return {"result": True, "data": {"count": total_count, "items": items}}
