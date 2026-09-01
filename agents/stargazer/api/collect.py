# -- coding: utf-8 --
# @File: collect.py
# @Time: 2025/2/27 10:41
# @Author: windyzhao
import json
import time
import uuid
from typing import List

from core.collection.application import get_collection_application
from core.collection.enums import WorkloadClass
from core.collection.request_builder import build_collection_request, parse_credentials_pool
from core.collection.request_identity import build_request_task_id_from_request
from core.collection.runtime import SubmissionStatus
from core.logger import logger
from plugins.base_utils import expand_ip_range
from sanic import Blueprint, response
from tasks.collectors.host_collector import _escape_prometheus_label_value

# 兼容旧测试/调用方私有名
_parse_credentials_pool = parse_credentials_pool

collect_router = Blueprint("collect", url_prefix="/collect")


def _request_task_id(request, params: dict | None = None) -> str:
    """薄租约 ID：规范化请求指纹；忽略调用方传入的 task_id。"""
    del params  # 保留形参以兼容旧调用；身份不再来自 params
    return build_request_task_id_from_request(request)


async def _submit_collection_run(request, task_params: dict, model_id: str):
    hosts_param = str(task_params.get("hosts") or "").strip()
    if hosts_param:
        task_params["hosts"] = _parse_hosts(hosts_param)
        if not task_params["hosts"]:
            raise ValueError("Failed to parse hosts parameter")
    task_params["credentials_pool"] = parse_credentials_pool(task_params.get("credentials_pool"), params=task_params)
    collection_request = build_collection_request(
        task_id=_request_task_id(request, task_params),
        params=task_params,
        workload_class=WorkloadClass.CONFIGURATION,
    )
    submission = await get_collection_application().submit(collection_request)
    http_status = {
        SubmissionStatus.ACCEPTED: 202,
        SubmissionStatus.DUPLICATE_ACTIVE: 202,
        SubmissionStatus.BUSY: 429,
    }[submission.status]
    timestamp = int(time.time() * 1000)
    metric = 'collection_request_accepted{{model_id="{}",task_id="{}",status="{}"}} 1 {}\n'.format(
        _escape_prometheus_label_value(model_id),
        _escape_prometheus_label_value(submission.task_id),
        _escape_prometheus_label_value(submission.status.value),
        timestamp,
    )
    headers = {
        "X-Task-ID": submission.task_id,
        "X-Task-Status": submission.status.value,
        "X-Fencing-Token": str(submission.fence),
        "X-Target-Count": str(len(collection_request.targets)),
    }
    if submission.status == SubmissionStatus.BUSY:
        headers["Retry-After"] = "1"
    if submission.summary:
        headers["X-Run-Summary"] = json.dumps(submission.summary, ensure_ascii=True, separators=(",", ":"))
    return response.raw(
        metric,
        content_type="text/plain; version=0.0.4; charset=utf-8",
        headers=headers,
        status=http_status,
    )


def _is_config_file_collect(task_params: dict) -> bool:
    plugin_name = str(task_params.get("plugin_name") or "")
    model_id = str(task_params.get("model_id") or "")
    return (
        str(task_params.get("callback_subject") or "") == "receive_config_file_result"
        or plugin_name in {"config_file_info", "network_config_file_info"}
        or model_id in {"config_file", "network_config_file"}
    )


def _validate_config_file_protocol(task_params: dict) -> str:
    if not _is_config_file_collect(task_params):
        return ""
    if str(task_params.get("protocol_version") or "") != "2":
        return "unsupported config collection protocol version"
    if task_params.get("target_instance_id") not in (None, ""):
        return "target_instance_id is no longer supported"

    target_instance_uuid = str(task_params.get("target_instance_uuid") or "").strip()
    try:
        parsed_uuid = uuid.UUID(target_instance_uuid)
    except (TypeError, ValueError, AttributeError):
        return "target_instance_uuid must be a valid UUIDv4"
    if parsed_uuid.version != 4 or str(parsed_uuid) != target_instance_uuid.lower():
        return "target_instance_uuid must be a canonical UUIDv4"
    return ""


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


@collect_router.get("/collect_info")
async def collect(request):
    """
    配置采集 - 异步模式
    立即返回请求接纳状态，实际采集由本 Pod 的统一异步运行时执行

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
    logger.info("event=plugin_collection_request_received")

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
            (
                'collection_request_error{model_id="",instance_id="'
                f'{_escape_prometheus_label_value(instance_id or "")}",error="model_id is Null"}} 1 {current_timestamp}'
            ),
        ]

        return response.raw("\n".join(error_lines) + "\n", content_type="text/plain; version=0.0.4; charset=utf-8", status=500)

    protocol_error = _validate_config_file_protocol(params)
    if protocol_error:
        return response.json({"error": protocol_error}, status=400)

    task_params = {
        **params,
        "tags": {
            "instance_id": instance_id,
            "instance_type": instance_type,
            "collect_type": collect_type,
            "config_type": config_type,
        },
    }
    try:
        return await _submit_collection_run(request, task_params, model_id)
    except ValueError as error:
        logger.warning("Collection request rejected: %s", error)
        return response.raw(
            f'collection_request_error{{model_id="{_escape_prometheus_label_value(model_id)}",error="invalid_request"}} 1\n',
            content_type="text/plain; version=0.0.4; charset=utf-8",
            status=400,
        )
    except Exception as error:  # Redis 不可用时 fail closed
        logger.error(
            "Collection request admission failed: %s",
            type(error).__name__,
            exc_info=True,
        )
        return response.raw(
            f'collection_request_error{{model_id="{_escape_prometheus_label_value(model_id)}",error="admission_unavailable"}} 1\n',
            content_type="text/plain; version=0.0.4; charset=utf-8",
            status=503,
        )


@collect_router.post("/pc_test_connection")
async def pc_test_connection(request):
    """
    PC 发现连接测试（HTTP debug 端点，同步返回）。

    复用真实 WinRM/SSH 链路执行最小只读身份命令：验证网络与认证、
    读取硬件 UUID/序列号，不执行软件扫描、不写 CMDB、不回传数据。

    请求体（JSON）：host, os_type(windows|macos), node_id, username, port,
    password|private_key|passphrase, winrm_scheme, winrm_transport, winrm_cert_validation。

    返回：{success, os_type, inst_name, hardware_uuid, serial_number, error_code, message}
    安全约束：请求体含秘密，绝不记录原始 body，错误只含稳定错误码。
    """
    from service.debug.pc_debug import run_pc_test_connection

    params = request.json or {}
    logger.info(
        "PC test connection request: os_type=%s host=%s",
        params.get("os_type"),
        params.get("host"),
    )
    try:
        result = await run_pc_test_connection(params)
    except Exception as e:  # noqa: BLE001 - 统一兜底为稳定错误码，不泄露内部细节
        logger.error("PC test connection unexpected error: %s", type(e).__name__)
        result = {
            "success": False,
            "os_type": "",
            "inst_name": "",
            "hardware_uuid": "",
            "serial_number": "",
            "error_code": "SCRIPT_OUTPUT_INVALID",
            "message": type(e).__name__,
        }
    return response.json(result, status=200)
