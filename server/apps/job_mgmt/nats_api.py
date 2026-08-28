"""Job Management NATS API - 用于数据权限规则"""

import os

import nats_client
from apps.core.logger import job_logger as logger
from apps.core.openapi.decorators import openapi_expose
from apps.core.utils.ssrf_validator import SSRFError, SSRFValidator
from apps.core.utils.viewset_utils import build_json_membership_query
from apps.job_mgmt.constants import CallbackType, ExecutionStatus, JobType, TriggerSource
from apps.job_mgmt.models import DistributionFile, JobExecution, Playbook, Script, Target
from apps.job_mgmt.openapi_serializers import FileDistributeRequestSerializer
from apps.job_mgmt.services.ansible_callback_service import handle_ansible_task_callback
from apps.job_mgmt.services.celery_dispatch import dispatch_celery_task
from apps.job_mgmt.services.dangerous_checker import DangerousChecker
from apps.job_mgmt.services.execution_cancellation_service import (
    ExecutionCancellationAuthorizationError,
    ExecutionCancellationError,
    request_execution_cancel,
)
from apps.job_mgmt.services.nats_module_service import get_module_data, get_module_list
from apps.job_mgmt.services.param_crypto import ParamCrypto
from apps.job_mgmt.services.script_normalize import normalize_script_line_endings
from apps.job_mgmt.services.script_params_service import ScriptParamsService
from apps.job_mgmt.tasks import distribute_files_task, execute_script_task
from apps.job_mgmt.utils.team_authz import is_team_authorized, normalize_team
from apps.node_mgmt.models import Node
from apps.system_mgmt.nats.common import _verify_token
from apps.system_mgmt.utils.group_utils import GroupUtils


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


_MAX_JOB_LIST_PAGE_SIZE = 100


def _masked_params(params):
    if not isinstance(params, list):
        return []
    return ParamCrypto.mask_encrypted_defaults(params)


def _parse_job_list_page(data: dict):
    try:
        page = int(data.get("page") or 1)
        page_size = int(data.get("page_size") or 20)
    except (TypeError, ValueError):
        return None, "page/page_size 参数非法"
    if page < 1:
        return None, "page 必须大于 0"
    if page_size < 1 or page_size > _MAX_JOB_LIST_PAGE_SIZE:
        return None, f"page_size 范围为 1-{_MAX_JOB_LIST_PAGE_SIZE}"
    return (page, page_size), None


def _team_owned_queryset(model, authorized_team_ids):
    queryset = model.objects.all()
    return queryset.filter(build_json_membership_query(queryset, "team", list(authorized_team_ids)))


def _paginate_queryset(queryset, page, page_size):
    total = queryset.count()
    start = (page - 1) * page_size
    return total, list(queryset.order_by("-updated_at", "-id")[start : start + page_size])


def _serialize_script_job(script):
    return {
        "id": script.id,
        "job_type": "script",
        "name": script.name,
        "description": script.description,
        "script_type": script.script_type,
        "params": _masked_params(script.params),
        "timeout": script.timeout,
        "is_built_in": script.is_built_in,
    }


def _serialize_playbook_job(playbook):
    return {
        "id": playbook.id,
        "job_type": "playbook",
        "name": playbook.name,
        "description": playbook.description,
        "version": playbook.version,
        "params": _masked_params(playbook.params),
    }


@nats_client.register
def job_list(data: dict):
    """返回当前团队可执行的作业模板列表（脚本库 + Playbook），含参数定义、不含脚本/包内容。

    供第三方 App 在执行前获取作业背景信息。
    Args:
        data: {"team": [...], "name": 可选模糊搜索, "page": 默认1, "page_size": 默认20，最大100}
    Returns:
        {"result": True, "data": {"scripts": {"count", "items"}, "playbooks": {"count", "items"}}}
    """
    authorized_team_ids = normalize_team((data or {}).get("team"))
    if not authorized_team_ids:
        return {"result": False, "message": "team 不能为空"}

    page_info, error = _parse_job_list_page(data or {})
    if error:
        return {"result": False, "message": error}
    page, page_size = page_info

    name = (data or {}).get("name") or ""
    scripts = _team_owned_queryset(Script, authorized_team_ids)
    playbooks = _team_owned_queryset(Playbook, authorized_team_ids)
    if name:
        scripts = scripts.filter(name__icontains=name)
        playbooks = playbooks.filter(name__icontains=name)

    script_count, script_rows = _paginate_queryset(scripts, page, page_size)
    playbook_count, playbook_rows = _paginate_queryset(playbooks, page, page_size)
    return {
        "result": True,
        "data": {
            "scripts": {"count": script_count, "items": [_serialize_script_job(item) for item in script_rows]},
            "playbooks": {"count": playbook_count, "items": [_serialize_playbook_job(item) for item in playbook_rows]},
        },
    }


@nats_client.register
def ansible_task_callback(data: dict):
    return handle_ansible_task_callback(data)


# ============================================================
# 开放接口：供第三方 App（如补丁管理）通过 NATS 调用
# ============================================================


@nats_client.register
def job_script_execute(data: dict, **_ignored):
    """脚本执行（NATS 开放接口）。忽略调用方 kwargs，身份固定为 api。"""
    return _run_script_execute(data)


def _run_script_execute(data: dict, *, trusted_actor=None):
    """
    脚本执行实现。

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
        trusted_actor: 仅网关封装传入的可信身份；NATS 入口不得传入。

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
    actor = trusted_actor if isinstance(trusted_actor, dict) else {}
    actor_name = actor.get("user") or "api"
    actor_domain = actor.get("domain") or "domain.com"

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
        executor_user=actor_name,
        created_by=actor_name[:32],
        updated_by=actor_name[:32],
        domain=actor_domain,
        updated_by_domain=actor_domain,
    )

    # 触发异步执行（Celery Worker）
    if not dispatch_celery_task(execute_script_task, execution):
        return {"result": False, "message": "任务调度服务暂不可用，请稍后重试"}

    return {"result": True, "data": {"task_id": execution.id}}


@nats_client.register
def job_file_distribute(data: dict):
    """旧版 NATS 文件分发入口；默认兼容，支持显式退役与即时回滚。"""
    if os.getenv("JOB_FILE_DISTRIBUTE_NATS_ENABLED", "1").strip().lower() not in {"1", "true", "yes", "on"}:
        logger.warning("[job_file_distribute] legacy NATS entry disabled")
        return {"result": False, "message": "旧版 NATS 文件分发入口已停用，请迁移至 OpenAPI 网关"}

    logger.info(
        "[job_file_distribute] legacy NATS call: team=%s, file_count=%s, target_count=%s",
        data.get("team"),
        len(data.get("file_keys") or []),
        len(data.get("target_list") or []),
    )
    return _run_file_distribute(data)


def _run_file_distribute(data: dict, *, trusted_actor=None):
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
    actor = trusted_actor if isinstance(trusted_actor, dict) else {}
    actor_name = actor.get("user") or "api"
    actor_domain = actor.get("domain") or "domain.com"

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
        executor_user=actor_name,
        # 通用 MaintainerInfo 字段历史上限为 32；完整可信身份保存在
        # executor_user + domain，维护人列仅作兼容投影，避免合法长账号落库失败。
        created_by=actor_name[:32],
        updated_by=actor_name[:32],
        domain=actor_domain,
        updated_by_domain=actor_domain,
    )

    # 触发异步执行（Celery Worker）
    if not dispatch_celery_task(distribute_files_task, execution):
        return {"result": False, "message": "任务调度服务暂不可用，请稍后重试"}

    return {"result": True, "data": {"task_id": execution.id}}


def _validate_openapi_target_scope(target_source, target_list, authorized_team_ids):
    """校验网关目标均属于可信身份绑定组织。"""
    id_field = "target_id" if target_source == "manual" else "node_id"
    target_ids = [item.get(id_field) for item in target_list]
    if any(not target_id for target_id in target_ids) or len(set(target_ids)) != len(target_ids):
        return f"目标列表必须包含唯一的 {id_field}"

    if target_source == "manual":
        targets = list(Target.objects.filter(id__in=target_ids))
        authorized = len(targets) == len(target_ids) and all(is_team_authorized(item.team, authorized_team_ids) for item in targets)
    else:
        authorized = Node.objects.filter(
            id__in=target_ids,
            nodeorganization__organization__in=authorized_team_ids,
        ).distinct().count() == len(target_ids)
    if not authorized:
        return "部分目标不存在或无权访问该组织的目标"
    return None


def _validate_openapi_distribute_scope(file_keys, target_source, target_list, authorized_team_ids):
    """校验网关文件与目标均属于可信身份绑定组织。"""
    files = list(DistributionFile.objects.filter(file_key__in=file_keys))
    if len({item.file_key for item in files}) != len(set(file_keys)) or any(not is_team_authorized(item.team, authorized_team_ids) for item in files):
        return "部分文件不存在、已过期或无权访问该组织的文件"
    return _validate_openapi_target_scope(target_source, target_list, authorized_team_ids)


@openapi_expose(
    path="job-mgmt/file-distribute",
    method="POST",
    schema=FileDistributeRequestSerializer,
    inject="team_list_with_user",
    summary="提交文件分发作业（组织口径：API 令牌绑定组织精确匹配，不级联子组织）",
)
def openapi_file_distribute(
    name,
    file_keys,
    target_source,
    target_list,
    target_path,
    overwrite_strategy,
    timeout,
    *,
    team=None,
    user_info=None,
):
    """经统一网关绑定可信组织后复用旧 NATS 文件分发实现。"""
    authorized_team_ids = normalize_team(team)
    authorized_team_id = next(iter(authorized_team_ids), None)
    if len(authorized_team_ids) != 1 or not GroupUtils.active_queryset(id=authorized_team_id).exists():
        return {"result": False, "message": "用户未关联活动团队"}

    scope_error = _validate_openapi_distribute_scope(file_keys, target_source, target_list, authorized_team_ids)
    if scope_error:
        id_field = "target_id" if target_source == "manual" else "node_id"
        logger.warning(
            "[openapi_file_distribute] scope rejected: user=%s domain=%s team=%s file_keys=%s " "target_source=%s target_ids=%s reason=%s",
            (user_info or {}).get("user", ""),
            (user_info or {}).get("domain", ""),
            authorized_team_id,
            file_keys,
            target_source,
            [item.get(id_field) for item in target_list],
            scope_error,
        )
        return {"result": False, "message": scope_error}

    result = _run_file_distribute(
        {
            "name": name,
            "file_keys": file_keys,
            "target_source": target_source,
            "target_list": target_list,
            "target_path": target_path,
            "overwrite_strategy": overwrite_strategy,
            "timeout": timeout,
            "team": [authorized_team_id],
            # 新入口暂不接受调用方控制的出站回调；调用方通过查询接口获取结果。
            "callback_type": CallbackType.WEB,
            "callback_url": "",
        },
        trusted_actor=user_info,
    )
    if not result.get("result"):
        return result
    return result.get("data") or {}


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
    if isinstance(task_id, bool) or not isinstance(task_id, int) or not 1 <= task_id <= 2**63 - 1:
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
