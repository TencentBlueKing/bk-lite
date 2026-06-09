# -- coding: utf-8 --
# @File: collect.py
# @Time: 2025/2/27 10:41
# @Author: windyzhao
import time
import uuid
import json
import base64
import re
from typing import List
from typing import Awaitable, Callable, Any

from sanic import Blueprint
from sanic.log import logger
from sanic import response

from core.credential_state_cache import CredentialStateCache
from core.task_queue import get_task_queue
from plugins.base_utils import expand_ip_range

collect_router = Blueprint("collect", url_prefix="/collect")


def _is_config_file_collect(task_params: dict) -> bool:
    return (
        str(task_params.get("callback_subject") or "") == "receive_config_file_result"
        or str(task_params.get("plugin_name") or "") == "config_file_info"
        or str(task_params.get("model_id") or "") == "config_file"
    )

def _get_connect_ip(host: str) -> str:
    host_str = str(host or "").strip()
    if not host_str:
        return ""
    return host_str.split("[", 1)[0].strip()


def _parse_hosts(hosts_param: str) -> List[str]:
    """
    解析hosts参数，支持逗号分隔和IP段
    
    支持格式：
    - 单个IP/域名: "192.168.1.1" 或 "ecs.cn-beijing.aliyuncs.com"
    - 逗号分隔: "192.168.1.1,192.168.1.2"
    - IP段: "192.168.1.1-192.168.1.10"
    - 混合: "192.168.1.1,192.168.1.5-192.168.1.8"
    
    Args:
        hosts_param: hosts参数字符串
        
    Returns:
        解析后的IP/域名列表
    """
    if not hosts_param or not hosts_param.strip():
        return []
    
    result = []
    segments = [seg.strip() for seg in hosts_param.split(",") if seg.strip()]
    
    for segment in segments:
        if "-" in segment and segment.count(".") >= 3:
            # 可能是IP段（192.168.1.1-192.168.1.10）
            try:
                expanded = expand_ip_range(segment)
                result.extend(expanded)
                logger.debug(f"Expanded IP range '{segment}' to {len(expanded)} IPs")
            except Exception as e:
                logger.warning(f"Failed to expand IP range '{segment}': {e}, treating as literal")
                result.append(segment)
        else:
            # 单个IP/域名/endpoint
            result.append(segment)
    
    return result


FLATTENED_CREDENTIAL_KEY_RE = re.compile(r"^credential_(\d+)_(.+)$")


def _parse_flattened_credentials_pool(params: dict | None = None) -> List[dict]:
    if not isinstance(params, dict) or not params:
        return []

    raw_count = params.get("credential_count")
    try:
        credential_count = int(raw_count)
    except (TypeError, ValueError):
        credential_count = 0

    grouped_credentials = {}
    for key, value in params.items():
        match = FLATTENED_CREDENTIAL_KEY_RE.match(str(key))
        if not match:
            continue
        index = int(match.group(1))
        field_name = match.group(2)
        grouped_credentials.setdefault(index, {})[field_name] = value

    if not grouped_credentials:
        return []

    if credential_count <= 0:
        credential_count = max(grouped_credentials) + 1

    credentials_pool = []
    for index in range(credential_count):
        credential = grouped_credentials.get(index)
        if isinstance(credential, dict) and credential:
            credentials_pool.append(credential)
    return credentials_pool


def _parse_credentials_pool(raw_value=None, params: dict | None = None) -> List[dict]:
    """解析可选的多凭据参数，优先兼容平铺 header，其次兼容旧 JSON/base64 格式。"""
    flattened_pool = _parse_flattened_credentials_pool(params)
    if flattened_pool:
        return flattened_pool

    if not raw_value:
        return []

    credentials_pool = raw_value
    if isinstance(raw_value, str):
        try:
            credentials_pool = json.loads(raw_value)
        except json.JSONDecodeError:
            try:
                decoded_value = base64.urlsafe_b64decode(raw_value.encode()).decode()
                credentials_pool = json.loads(decoded_value)
            except Exception:
                logger.warning("Failed to parse credentials_pool payload, fallback to single credential mode")
                return []

    if not isinstance(credentials_pool, list):
        return []

    return [item for item in credentials_pool if isinstance(item, dict)]


def _build_credential_results_payload(events: List[dict]) -> dict:
    next_since = ""
    for item in events or []:
        finished_at = str((item or {}).get("finished_at") or "")
        if finished_at and finished_at > next_since:
            next_since = finished_at
    return {"results": events or [], "next_since": next_since}


def _build_collect_task_candidates(task_params: dict, hosts_list: List[str], credentials_pool: List[dict]) -> dict[str, List[dict]]:
    """先生成每个 host 的候选任务组合，后续再按缓存/冷却规则筛选是否入队。"""
    base_task_params = {k: v for k, v in task_params.items() if k != "credentials_pool"}
    candidates_by_host: dict[str, List[dict]] = {}

    for host in hosts_list:
        if not credentials_pool:
            candidates_by_host[host] = [{**base_task_params, "host": host}]
            continue

        candidates_by_host[host] = [
            {
                **base_task_params,
                **credential,
                "host": host,
                "credential_index": credential_index,
                "credentials_pool": credentials_pool,
            }
            for credential_index, credential in enumerate(credentials_pool)
        ]

    return candidates_by_host


def _select_collect_task_candidates(
    candidates_by_host: dict[str, List[dict]],
    collect_task_id,
    cache_state_getter,
) -> List[dict]:
    selected_tasks = []

    for host, candidates in candidates_by_host.items():
        if not candidates:
            continue

        if not candidates[0].get("credential_id"):
            selected_tasks.append(candidates[0])
            continue

        success_credential_id = cache_state_getter(collect_task_id, host)
        if success_credential_id:
            matched_candidate = next(
                (candidate for candidate in candidates if candidate.get("credential_id") == success_credential_id),
                None,
            )
            if matched_candidate is not None:
                failure_state = cache_state_getter(collect_task_id, host, success_credential_id) or {}
                if not failure_state.get("is_cooled"):
                    selected_tasks.append(matched_candidate)
                    continue

        for candidate in candidates:
            credential_id = candidate.get("credential_id")
            failure_state = cache_state_getter(collect_task_id, host, credential_id) or {}
            if failure_state.get("is_cooled"):
                continue
            selected_tasks.append(candidate)
            break

    return selected_tasks


async def _select_collect_task_candidates_async(
    candidates_by_host: dict[str, List[dict]],
    collect_task_id,
    cache_state_getter,
) -> List[dict]:
    selected_tasks = []

    for host, candidates in candidates_by_host.items():
        if not candidates:
            continue

        if not candidates[0].get("credential_id"):
            selected_tasks.append(candidates[0])
            continue

        success_credential_id = await cache_state_getter(collect_task_id, host)
        if success_credential_id:
            matched_candidate = next(
                (candidate for candidate in candidates if candidate.get("credential_id") == success_credential_id),
                None,
            )
            if matched_candidate is not None:
                failure_state = await cache_state_getter(collect_task_id, host, success_credential_id) or {}
                if not failure_state.get("is_cooled"):
                    selected_tasks.append(matched_candidate)
                    continue

        for candidate in candidates:
            credential_id = candidate.get("credential_id")
            failure_state = await cache_state_getter(collect_task_id, host, credential_id) or {}
            if failure_state.get("is_cooled"):
                continue
            selected_tasks.append(candidate)
            break

    return selected_tasks


@collect_router.get("/credential_results")
async def get_credential_results(request):
    raw_limit = request.args.get("limit") or 500
    try:
        limit = max(1, min(int(raw_limit), 2000))
    except (TypeError, ValueError):
        limit = 500

    events = await CredentialStateCache.list_result_events(
        since=request.args.get("since") or "",
        limit=limit,
    )
    return response.json(_build_credential_results_payload(events))


def _expand_collect_tasks(task_params: dict, hosts_list: List[str], credentials_pool: List[dict], cache_state_getter=None) -> List[dict]:
    """根据 hosts 与缓存命中态生成首轮单 host / 单凭据任务列表。"""
    cache_state_getter = cache_state_getter or _get_cached_credential_state
    collect_task_id = task_params.get("collect_task_id")
    candidates_by_host = _build_collect_task_candidates(task_params, hosts_list, credentials_pool)
    return _select_collect_task_candidates(candidates_by_host, collect_task_id, cache_state_getter)


def _get_cached_credential_state(collect_task_id, host: str, credential_id: str | None = None):
    return None


async def _get_cached_credential_state_async(collect_task_id, host: str, credential_id: str | None = None):
    if collect_task_id in (None, "") or not host:
        return None
    if credential_id is None:
        return await CredentialStateCache.get_success_credential(collect_task_id, host)
    return await CredentialStateCache.get_failure_state(collect_task_id, host, credential_id)


async def _expand_collect_tasks_async(
    task_params: dict,
    hosts_list: List[str],
    credentials_pool: List[dict],
    cache_state_getter: Callable[[Any, str, str | None], Awaitable[Any]] | None = None,
) -> List[dict]:
    cache_state_getter = cache_state_getter or _get_cached_credential_state_async
    collect_task_id = task_params.get("collect_task_id")
    candidates_by_host = _build_collect_task_candidates(task_params, hosts_list, credentials_pool)
    return await _select_collect_task_candidates_async(candidates_by_host, collect_task_id, cache_state_getter)


@collect_router.get("/collect_info")
async def collect(request):
    """
    配置采集 - 异步模式
    立即返回请求已接收的指标，实际采集任务放入队列异步执行

    参数来源：
    - Headers: cmdb* 开头的参数
    - Query: URL 参数（向后兼容）

    必需参数：
        plugin_name: 插件名称 (mysql_info, redis_info 等)

    可选 Tags 参数（Headers，由 Telegraf 传递）：
        X-Instance-ID: 实例标识
        X-Instance-Type: 实例类型
        X-Collect-Type: 采集类型（默认 discovery）
        X-Config-Type: 配置类型

    示例请求：
        curl -X GET "http://localhost:8083/api/collect/collect_info" \
             -H "cmdbplugin_name: mysql_info" \
             -H "cmdbhostname: 192.168.1.100" \
             -H "cmdbport: 3306" \
             -H "cmdbusername: root" \
             -H "cmdbpassword: ********" \
             -H "X-Instance-ID: mysql-192.168.1.100" \
             -H "X-Instance-Type: mysql" \
             -H "X-Collect-Type: discovery" \
             -H "X-Config-Type: auto"

    返回：
        Prometheus 格式的"请求已接收"指标，包含 task_id 用于追踪
    """
    logger.info("=== Plugin collection request received ===")

    # Sanic 要求请求体被消费（即使是 GET 请求），否则可能出现
    # "<Request ...> body not consumed." 日志告警。
    await request.receive_body()

    # 1. 解析参数（兼容旧逻辑）
    params = {k.split("cmdb", 1)[-1]: v for k, v in dict(request.headers).items() if k.startswith("cmdb")}
    if not params:
        params = {i[0]: i[1] for i in request.query_args}

    # 2. 提取 Tags（从 Headers）
    instance_id = request.headers.get("instance_id")
    instance_type = request.headers.get("instance_type")
    collect_type = request.headers.get("collect_type")
    config_type = request.headers.get("config_type")

    model_id = params.get("model_id")
    if not model_id:
        # 返回错误指标
        current_timestamp = int(time.time() * 1000)
        error_lines = [
            "# HELP collection_request_error Collection request error",
            "# TYPE collection_request_error gauge",
            f'collection_request_error{{model_id="",instance_id="{instance_id}",error="model_id is Null"}} 1 {current_timestamp}'
        ]

        return response.raw(
            "\n".join(error_lines) + "\n",
            content_type='text/plain; version=0.0.4; charset=utf-8',
            status=500
        )


    try:
        # 3. 构建基础任务参数
        task_params = {
            **params,  # 原有参数（包含 plugin_name）
            # Tags 参数（5个核心标签）
            "tags": {
                "instance_id": instance_id,
                "instance_type": instance_type,
                "collect_type": collect_type,
                "config_type": config_type,
            }
        }

        # 4. 获取任务队列
        task_queue = get_task_queue()
        
        # 5. 检查是否有hosts参数
        hosts_param = params.get("hosts", "").strip()
        credentials_pool = _parse_credentials_pool(params.get("credentials_pool"), params=params)
        
        if hosts_param:
            # ========== 场景A：有hosts参数 → 拆分任务 ==========
            hosts_list = _parse_hosts(hosts_param)
            
            if not hosts_list:
                # hosts参数解析为空
                current_timestamp = int(time.time() * 1000)
                error_lines = [
                    "# HELP collection_request_error Collection request error",
                    "# TYPE collection_request_error gauge",
                    f'collection_request_error{{model_id="{model_id}",error="Failed to parse hosts parameter"}} 1 {current_timestamp}'
                ]
                return response.raw(
                    "\n".join(error_lines) + "\n",
                    content_type='text/plain; version=0.0.4; charset=utf-8',
                    status=400
                )
            
            # 生成批次ID
            batch_id = f"batch_{uuid.uuid4().hex[:16]}"
            expanded_tasks = await _expand_collect_tasks_async(task_params, hosts_list, credentials_pool)
            
            logger.info("=" * 70)
            logger.info(f"📦 Task splitting: {len(hosts_list)} host(s) → {len(expanded_tasks)} task(s)")
            logger.info(f"📋 Batch ID: {batch_id}")
            logger.info(f"🎯 Model: {model_id}")
            logger.info("=" * 70)
            
            task_infos = []
            success_count = 0
            failed_count = 0
            
            # 循环每个 host/credential 组合创建任务
            for idx, single_task in enumerate(expanded_tasks, 1):
                try:
                    host = single_task.get("host", "")
                    single_host_params = {
                        **single_task,
                        "batch_id": batch_id,
                        "batch_index": idx,
                        "batch_total": len(expanded_tasks),
                    }
                    if _is_config_file_collect(task_params):
                        # 配置文件采集回调由 CMDB 按实例名称反查 _id，这里只保留拆分后的 host 和连接 IP。
                        single_host_params.pop("connect_ip", None)
                        single_host_params.pop("target_instance_id", None)
                        single_host_params["connect_ip"] = _get_connect_ip(host)
                    
                    # 创建任务
                    task_info = await task_queue.enqueue_collect_task(single_host_params)
                    task_infos.append({
                        "host": host,
                        "task_id": task_info["task_id"],
                        "job_id": task_info.get("job_id", ""),
                        "status": task_info["status"]
                    })
                    
                    if task_info["status"] == "queued":
                        success_count += 1
                        logger.info(f"  ✅ [{idx}/{len(expanded_tasks)}] {host}: {task_info['task_id']}")
                    else:
                        logger.warning(f"  ⚠️  [{idx}/{len(expanded_tasks)}] {host}: {task_info['status']}")
                        
                except Exception as e:
                    failed_count += 1
                    host = single_task.get("host", "")
                    logger.error(f"  ❌ [{idx}/{len(expanded_tasks)}] {host}: {e}")
                    task_infos.append({
                        "host": host,
                        "task_id": "",
                        "status": "failed",
                        "error": str(e)
                    })
            
            # 输出汇总
            skipped_count = len(expanded_tasks) - success_count - failed_count
            logger.info("=" * 70)
            logger.info(f"📊 Summary: {success_count} queued, {failed_count} failed, {skipped_count} skipped")
            logger.info("=" * 70)
            
            # 返回批次响应
            current_timestamp = int(time.time() * 1000)
            prometheus_lines = [
                "# HELP collection_batch_accepted Indicates that collection batch was accepted",
                "# TYPE collection_batch_accepted gauge",
                f'collection_batch_accepted{{model_id="{model_id}",batch_id="{batch_id}",total="{len(expanded_tasks)}",queued="{success_count}",failed="{failed_count}"}} 1 {current_timestamp}'
            ]
            
            return response.raw(
                "\n".join(prometheus_lines) + "\n",
                content_type='text/plain; version=0.0.4; charset=utf-8',
                headers={
                    'X-Batch-ID': batch_id,
                    'X-Task-Count': str(len(task_infos)),
                    'X-Success-Count': str(success_count)
                }
            )
        else:
            # ========== 场景B：无hosts参数 → 单任务 ==========
            # 云采集使用默认endpoint，或单IP采集
            logger.info(f"📦 Single task mode: model={model_id}")
            
            task_info = await task_queue.enqueue_collect_task(task_params)
            task_status = task_info.get("status", "unknown")
            logger.info(
                f"Plugin task enqueue result: task_id={task_info['task_id']}, "
                f"status={task_status}, model_id={model_id}, job_id={task_info.get('job_id', '')}"
            )
            
            # 返回单任务响应
            current_timestamp = int(time.time() * 1000)
            prometheus_lines = [
                "# HELP collection_request_accepted Indicates that collection request was accepted",
                "# TYPE collection_request_accepted gauge",
                f'collection_request_accepted{{model_id="{model_id}",task_id="{task_info["task_id"]}",status="{task_status}"}} 1 {current_timestamp}'
            ]
            
            return response.raw(
                "\n".join(prometheus_lines) + "\n",
                content_type='text/plain; version=0.0.4; charset=utf-8',
                headers={
                    'X-Task-ID': task_info['task_id'],
                    'X-Job-ID': task_info.get('job_id', ""),
                    'X-Task-Status': task_status
                }
            )

    except Exception as e:
        logger.error(f"Error queuing plugin task: {e}", exc_info=True)

        # 返回错误指标
        current_timestamp = int(time.time() * 1000)
        error_lines = [
            "# HELP collection_request_error Collection request error",
            "# TYPE collection_request_error gauge",
            f'collection_request_error{{model_id="{model_id}",error="{str(e)}"}} 1 {current_timestamp}'
        ]

        return response.raw(
            "\n".join(error_lines) + "\n",
            content_type='text/plain; version=0.0.4; charset=utf-8',
            status=500
        )
