"""Job Management NATS API - 用于数据权限规则"""

from asgiref.sync import async_to_sync
from celery import current_app
from django.utils import timezone

import nats_client
from apps.core.logger import job_logger as logger
from apps.core.utils.ssrf_validator import SSRFError, SSRFValidator
from apps.job_mgmt.constants import CallbackType, ExecutionStatus, JobType, TriggerSource
from apps.job_mgmt.models import DangerousPath, DangerousRule, DistributionFile, JobExecution, Playbook, ScheduledTask, Script, Target
from apps.job_mgmt.services.callback_service import send_callback
from apps.job_mgmt.services.dangerous_checker import DangerousChecker
from apps.job_mgmt.services.execution_stream_service import publish_done_sentinel
from apps.job_mgmt.services.script_params_service import ScriptParamsService
from apps.job_mgmt.tasks import distribute_files_task, execute_script_task, finalize_cancelling_execution
from apps.node_mgmt.utils.s3 import delete_s3_file
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
def get_job_mgmt_module_data(module, child_module, page, page_size, group_id):
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
        model = model_map[module]
    else:
        model = system_model_map[child_module]

    queryset = model.objects.filter(team__contains=int(group_id))

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
    script = Script.objects.filter(id=script_id).first()
    if not script:
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


@nats_client.register
def ansible_task_callback(data: dict):
    """
    Ansible 任务执行回调

    由新版本 Ansible Executor 执行完成后调用，更新 JobExecution 状态和结果。

    仅支持结构化的 per-host 结果数组，不再兼容旧版字符串输出。

    所有异常分支都必须收敛到终态（FAILED），避免作业永久 RUNNING。

    Args:
        data: 回调数据，包含以下字段：
            - task_id: 任务ID（对应 JobExecution.id）
            - task_type: 任务类型（adhoc/playbook）
            - status: 执行状态（success/failed）
            - success: 任务级是否成功
            - result: per-host 结果数组，每项至少包含 host/status/stdout/stderr/exit_code/error_message
            - error: 错误信息
            - started_at: 开始时间（ISO格式）
            - finished_at: 结束时间（ISO格式）

    Returns:
        {"success": True/False, "message": "..."}
    """
    logger.info("[ansible_task_callback] %s", summarize_ansible_callback(data))

    task_id = data.get("task_id")
    if not task_id:
        logger.warning("[ansible_task_callback] 缺少 task_id")
        return {"success": False, "message": "缺少 task_id"}

    try:
        execution = JobExecution.objects.get(id=task_id)
    except JobExecution.DoesNotExist:
        logger.warning(f"[ansible_task_callback] 执行记录不存在: task_id={task_id}")
        return {"success": False, "message": f"执行记录不存在: {task_id}"}

    # 检查是否已经是终态（避免重复处理）
    if execution.status in ExecutionStatus.TERMINAL_STATES:
        logger.info(f"[ansible_task_callback] 任务已处于终态: task_id={task_id}, status={execution.status}")
        return {"success": True, "message": "任务已处理"}

    # CANCELLING 是非终态：真实结果仍正常落库，但最终状态收敛为 CANCELLED（修复取消后结果被丢弃）
    was_cancelling = execution.status == ExecutionStatus.CANCELLING

    # 辅助函数：将执行记录收敛到 FAILED 终态
    def _fail_execution(error_message: str):
        """将执行记录收敛到 FAILED 终态"""
        safe_error_message = str(sanitize_sensitive_data(error_message))
        target_list_for_fail = execution.target_list or []
        execution.status = ExecutionStatus.FAILED
        execution.finished_at = timezone.now()
        execution.execution_results = [
            {
                "target_key": str(t.get("target_id", "")),
                "name": t.get("name", ""),
                "ip": t.get("ip", ""),
                "status": ExecutionStatus.FAILED,
                "stdout": "",
                "stderr": safe_error_message,
                "exit_code": 1,
                "error_message": safe_error_message,
                "started_at": execution.started_at.isoformat() if execution.started_at else "",
                "finished_at": timezone.now().isoformat(),
            }
            for t in target_list_for_fail
        ]
        execution.success_count = 0
        execution.failed_count = len(target_list_for_fail)
        execution.save(
            update_fields=[
                "status",
                "execution_results",
                "finished_at",
                "success_count",
                "failed_count",
                "updated_at",
            ]
        )
        logger.warning("[ansible_task_callback] 任务异常收敛到 FAILED: task_id=%s, reason=%s", task_id, safe_error_message)
        # 为各目标补发 done 哨兵，关闭前端实时流面板（避免空等到 idle 超时）
        for t in target_list_for_fail:
            publish_done_sentinel(execution.id, str(t.get("target_id", "")), ExecutionStatus.FAILED)
        send_callback(execution)

    # 解析新版本结构化回调数据
    raw_result = data.get("result", [])
    error_output = str(sanitize_sensitive_data(data.get("error", "")))
    finished_at_str = data.get("finished_at")
    target_list = execution.target_list or []
    execution_results = []

    if not (isinstance(raw_result, list) and raw_result and all(isinstance(item, dict) for item in raw_result)):
        _fail_execution(f"回调结果格式非法: {sanitize_sensitive_data(raw_result)}")
        return {"success": False, "message": "非法的新版本结果格式，已收敛到 FAILED"}

    target_map = {}
    for target_info in target_list:
        target_map[str(target_info.get("ip", ""))] = target_info
        target_map[str(target_info.get("target_id", ""))] = target_info

    seen_target_keys = set()
    for host_result in raw_result:
        host_key = str(host_result.get("host", ""))
        target_info = target_map.get(host_key)
        if not target_info:
            _fail_execution(f"结果中的主机未匹配到目标: {host_key}")
            return {"success": False, "message": f"结果中的主机未匹配到目标: {host_key}，已收敛到 FAILED"}

        target_key = str(target_info.get("target_id", ""))
        if target_key in seen_target_keys:
            _fail_execution(f"结果中的主机重复: {host_key}")
            return {"success": False, "message": f"结果中的主机重复: {host_key}，已收敛到 FAILED"}
        seen_target_keys.add(target_key)

        host_status = host_result.get("status")
        final_status = ExecutionStatus.SUCCESS if host_status == "success" else ExecutionStatus.FAILED
        execution_results.append(
            {
                "target_key": target_key,
                "name": target_info.get("name", host_key),
                "ip": target_info.get("ip", host_key),
                "status": final_status,
                "stdout": str(sanitize_sensitive_data(str(host_result.get("stdout", "")))),
                "stderr": str(sanitize_sensitive_data(str(host_result.get("stderr", "")))),
                "exit_code": host_result.get("exit_code", 0),
                "error_message": str(sanitize_sensitive_data(str(host_result.get("error_message", "")))),
                "started_at": execution.started_at.isoformat() if execution.started_at else "",
                "finished_at": finished_at_str or timezone.now().isoformat(),
            }
        )

    if len(execution_results) < len(target_list):
        existing_keys = {item["target_key"] for item in execution_results}
        for target_info in target_list:
            target_key = str(target_info.get("target_id", ""))
            if target_key in existing_keys:
                continue
            execution_results.append(
                {
                    "target_key": target_key,
                    "name": target_info.get("name", ""),
                    "ip": target_info.get("ip", ""),
                    "status": ExecutionStatus.FAILED,
                    "stdout": "",
                    "stderr": str(error_output or "未收到该目标执行结果"),
                    "exit_code": 1,
                    "error_message": str(error_output or "未收到该目标执行结果"),
                    "started_at": execution.started_at.isoformat() if execution.started_at else "",
                    "finished_at": finished_at_str or timezone.now().isoformat(),
                }
            )

    # 更新执行记录：取消中(CANCELLING)的任务收敛为 CANCELLED 终态，其余按真实结果写 SUCCESS/FAILED
    if was_cancelling:
        execution.status = ExecutionStatus.CANCELLED
    else:
        execution.status = (
            ExecutionStatus.FAILED if any(item.get("status") == ExecutionStatus.FAILED for item in execution_results) else ExecutionStatus.SUCCESS
        )
    execution.execution_results = execution_results
    execution.finished_at = timezone.now()
    execution.success_count = sum(1 for item in execution_results if item.get("status") == ExecutionStatus.SUCCESS)
    execution.failed_count = sum(1 for item in execution_results if item.get("status") == ExecutionStatus.FAILED)
    execution.save(
        update_fields=[
            "status",
            "execution_results",
            "finished_at",
            "success_count",
            "failed_count",
            "updated_at",
        ]
    )

    # 为各目标补发 done 哨兵，关闭前端实时流面板（ansible 异步回调收尾）
    for item in execution_results:
        publish_done_sentinel(execution.id, item.get("target_key", ""), item.get("status", ExecutionStatus.SUCCESS))

    logger.info(f"[ansible_task_callback] 任务完成: task_id={task_id}, status={execution.status}")

    # 清理 Playbook 执行中转到 NATS OS 的临时文件
    if execution.playbook_id:
        nats_file_key = f"job-playbooks/{task_id}/{execution.playbook.file_name}" if execution.playbook else None
        if nats_file_key:
            try:
                async_to_sync(delete_s3_file)(nats_file_key)
                logger.info(f"[ansible_task_callback] 已清理 NATS OS 中转文件: {nats_file_key}")
            except Exception as e:
                logger.warning(f"[ansible_task_callback] 清理 NATS OS 中转文件失败: {nats_file_key}, error={e}")

    # 回调通知（如有 callback_url）
    send_callback(execution)

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
    result = execute_script_task.delay(execution.id)
    execution.celery_task_id = result.id
    execution.save(update_fields=["celery_task_id", "updated_at"])

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
    if not team:
        return {"result": False, "message": "team 不能为空"}

    # 回调配置校验（web 通道 SSRF 校验、nats 通道 subject 必填）
    cb_err = _validate_callback_config(callback_type, callback_url, callback_subject, "job_file_distribute")
    if cb_err:
        return {"result": False, "message": cb_err}

    # 高危路径检测
    check_result = DangerousChecker.check_path(target_path, team)
    if not check_result.can_execute:
        forbidden_rules = [r["rule_name"] for r in check_result.forbidden]
        return {"result": False, "message": f"目标路径为高危路径，禁止分发: {', '.join(forbidden_rules)}"}

    # 验证文件存在
    distribution_files = DistributionFile.objects.filter(file_key__in=file_keys)
    found_keys = set(distribution_files.values_list("file_key", flat=True))
    missing_keys = [k for k in file_keys if k not in found_keys]
    if missing_keys:
        return {"result": False, "message": f"部分文件不存在或已过期: {', '.join(missing_keys)}"}

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
    result = distribute_files_task.delay(execution.id)
    execution.celery_task_id = result.id
    execution.save(update_fields=["celery_task_id", "updated_at"])

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


@nats_client.register
def job_detail_query(data: dict):
    """
    查询单个作业详情（NATS 开放接口）

    Args:
        data: {"task_id": 123}

    Returns:
        {"result": True, "data": {...}} 或 {"result": False, "message": "..."}
    """
    task_id = data.get("task_id")
    if not task_id:
        return {"result": False, "message": "task_id 不能为空"}

    try:
        execution = JobExecution.objects.get(id=task_id)
    except JobExecution.DoesNotExist:
        return {"result": False, "message": "任务不存在"}

    return {
        "result": True,
        "data": {
            "task_id": execution.id,
            "name": execution.name,
            "job_type": execution.job_type,
            "status": execution.status,
            "script_type": execution.script_type,
            "script_content": execution.script_content,
            "timeout": execution.timeout,
            "started_at": execution.started_at.isoformat() if execution.started_at else None,
            "finished_at": execution.finished_at.isoformat() if execution.finished_at else None,
            "total_count": execution.total_count,
            "success_count": execution.success_count,
            "failed_count": execution.failed_count,
            "target_list": execution.target_list,
            "execution_results": execution.execution_results,
        },
    }


@nats_client.register
def job_task_terminate(data=None, task_id=None, **kwargs):
    if isinstance(data, dict):
        task_id = data.get("task_id", task_id)
    if task_id is None:
        task_id = kwargs.get("task_id")
    if not task_id:
        return {"result": False, "message": "task_id 不能为空"}

    try:
        execution = JobExecution.objects.get(id=task_id)
    except JobExecution.DoesNotExist:
        return {"result": False, "message": "任务不存在"}

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
