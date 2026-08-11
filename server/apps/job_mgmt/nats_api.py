"""Job Management NATS API - 用于数据权限规则"""

import nats_client
from apps.core.logger import job_logger as logger
from apps.core.utils.ssrf_validator import SSRFError, SSRFValidator
from apps.job_mgmt.constants import CallbackType, ExecutionStatus, JobType, TriggerSource
from apps.job_mgmt.models import DistributionFile, JobExecution, Script, Target
from apps.job_mgmt.services.ansible_callback_service import handle_ansible_task_callback
from apps.job_mgmt.services.celery_dispatch import dispatch_celery_task
from apps.job_mgmt.services.dangerous_checker import DangerousChecker
from apps.job_mgmt.services.execution_cancellation_service import (
    ExecutionCancellationAuthorizationError,
    ExecutionCancellationError,
    request_execution_cancel,
)
from apps.job_mgmt.services.nats_module_service import get_module_data, get_module_list
from apps.job_mgmt.services.script_normalize import normalize_script_line_endings
from apps.job_mgmt.services.script_params_service import ScriptParamsService
from apps.job_mgmt.tasks import distribute_files_task, execute_script_task
from apps.job_mgmt.utils.team_authz import is_team_authorized, normalize_team
from apps.system_mgmt.nats.common import _verify_token


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
    return get_module_list()


@nats_client.register
def get_job_mgmt_module_data(module, child_module, page, page_size, group_id, *, team=None):
    """获取作业管理模块数据"""
    return get_module_data(module, child_module, page, page_size, group_id, team=team)


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


@nats_client.register
def ansible_task_callback(data: dict):
    return handle_ansible_task_callback(data)


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
        caller_token = data.get("caller_token", kwargs.get("caller_token", ""))
    else:
        caller_token = kwargs.get("caller_token", "")
    if task_id is None:
        task_id = kwargs.get("task_id")
    if isinstance(task_id, str):
        normalized_task_id = task_id.strip()
        if normalized_task_id.isdecimal():
            try:
                task_id = int(normalized_task_id)
            except ValueError:
                task_id = None
    if (
        isinstance(task_id, bool)
        or not isinstance(task_id, int)
        or not 1 <= task_id <= 2**63 - 1
    ):
        return {"result": False, "message": "task_id 必须为正整数或其字符串形式"}
    if not caller_token:
        return {"result": False, "message": "caller_token 不能为空"}

    try:
        caller = _verify_token(caller_token)
    except Exception:
        return {"result": False, "message": "Unauthorized: invalid caller_token"}

    caller_team = normalize_team(getattr(caller, "group_list", []))
    if not caller_team:
        logger.warning("[job_task_terminate] 服务端团队归属校验失败: task_id=%s", task_id)
        return {"result": False, "message": "无权取消该任务"}

    try:
        execution, message = request_execution_cancel(task_id, authorized_team_ids=caller_team)
    except JobExecution.DoesNotExist:
        return {"result": False, "message": "任务不存在"}
    except ExecutionCancellationAuthorizationError as error:
        logger.warning("[job_task_terminate] 锁内团队归属校验失败: task_id=%s", task_id)
        return {"result": False, "message": str(error)}
    except ExecutionCancellationError as error:
        return {"result": False, "message": str(error)}
    return {
        "result": True,
        "data": {"task_id": execution.id, "status": execution.status, "message": message},
    }


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
