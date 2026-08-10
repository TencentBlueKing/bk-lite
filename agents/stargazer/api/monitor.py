import time
from typing import Any, Callable

from sanic import Blueprint
from sanic import response
from sanic.exceptions import SanicException
from core.logger import logger

from core.collection.application import get_collection_application
from core.collection.request_builder import build_collection_request
from core.collection.request_identity import build_request_task_id_from_request

monitor_router = Blueprint("monitor", url_prefix="/monitor")

_PROMETHEUS_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"


async def _submit_monitor_request(request, task_params: dict) -> dict:
    task_id = build_request_task_id_from_request(request)
    try:
        collection_request = build_collection_request(
            task_id=task_id,
            params=task_params,
        )
    except ValueError as error:
        raise SanicException(str(error), status_code=400) from error
    submission = await get_collection_application().submit(collection_request)
    if submission.status.value == "busy":
        raise SanicException("collection-runtime-busy", status_code=429)
    return {
        "task_id": submission.task_id,
        "status": submission.status.value,
        "fence": submission.fence,
        "http_status": 202,
    }


def _mask_credential(secret_id: str) -> str:
    """对凭证 ID 做脱敏处理，仅保留前4位便于区分账号，不暴露完整凭证值。"""
    if not secret_id:
        return "***"
    return secret_id[:4] + "***" if len(secret_id) > 4 else "***"


def _prometheus_labels(**labels: Any) -> str:
    parts = []
    for key, value in labels.items():
        if value is None:
            continue
        parts.append(f'{key}="{value}"')
    return ",".join(parts)


def _monitor_error_response(
    monitor_type: str,
    error: str,
    status: int = 400,
    **extra_labels: Any,
):
    current_timestamp = int(time.time() * 1000)
    labels = _prometheus_labels(
        monitor_type=monitor_type, error=error, **extra_labels
    )
    error_lines = [
        "# HELP monitor_request_error Monitor request error",
        "# TYPE monitor_request_error gauge",
        f"monitor_request_error{{{labels}}} 1 {current_timestamp}",
    ]
    return response.raw(
        "\n".join(error_lines) + "\n",
        content_type=_PROMETHEUS_CONTENT_TYPE,
        status=status,
    )


def _monitor_accepted_response(
    monitor_type: str,
    task_info: dict,
    *,
    extra_headers: dict[str, str] | None = None,
    **extra_labels: Any,
):
    current_timestamp = int(time.time() * 1000)
    # 标签顺序需与历史响应一致：monitor_type → 业务标签 → task_id → status
    labels = _prometheus_labels(
        monitor_type=monitor_type,
        **extra_labels,
        task_id=task_info["task_id"],
        status=task_info["status"],
    )
    prometheus_lines = [
        "# HELP monitor_request_accepted Indicates that monitor request was accepted",
        "# TYPE monitor_request_accepted gauge",
        f"monitor_request_accepted{{{labels}}} 1 {current_timestamp}",
    ]
    headers = {
        "X-Task-ID": task_info["task_id"],
        "X-Task-Status": task_info["status"],
        "X-Fencing-Token": str(task_info["fence"]),
    }
    if extra_headers:
        headers.update(extra_headers)
    return response.raw(
        "\n".join(prometheus_lines) + "\n",
        content_type=_PROMETHEUS_CONTENT_TYPE,
        headers=headers,
        status=task_info["http_status"],
    )


def _standard_tags(request, *, defaults: dict[str, str] | None = None) -> dict:
    defaults = defaults or {}
    return {
        "agent_id": request.headers.get("agent_id", defaults.get("agent_id", "")),
        "instance_id": request.headers.get(
            "instance_id", defaults.get("instance_id")
        ),
        "instance_type": request.headers.get(
            "instance_type", defaults.get("instance_type")
        ),
        "collect_type": request.headers.get(
            "collect_type", defaults.get("collect_type")
        ),
        "config_type": request.headers.get(
            "config_type", defaults.get("config_type")
        ),
    }


async def _run_monitor_handler(
    request,
    *,
    monitor_type: str,
    build_params: Callable[[Any], dict],
    accept_labels: Callable[[dict], dict],
    error_labels: Callable[[], dict] | None = None,
    extra_headers: dict[str, str] | None = None,
    log_name: str | None = None,
):
    display = log_name or monitor_type
    logger.info("=== %s metrics collection request received ===", display)
    try:
        task_params = build_params(request)
        task_info = await _submit_monitor_request(request, task_params)
        logger.info("%s metrics run accepted: %s", display, task_info["task_id"])
        return _monitor_accepted_response(
            monitor_type,
            task_info,
            extra_headers=extra_headers,
            **accept_labels(task_params),
        )
    except SanicException:
        raise
    except Exception as error:
        logger.error(
            "Error queuing %s metrics task: %s", display, error, exc_info=True
        )
        labels = error_labels() if error_labels else {}
        return _monitor_error_response(
            monitor_type, str(error), status=500, **labels
        )


@monitor_router.get("/vmware/metrics")
async def vmware_metrics(request):
    def build_params(req):
        minutes = req.args.get("minutes", 5)
        host = req.headers.get("host")
        logger.info("Request: Host=%s, Minutes=%s", host, minutes)
        return {
            "monitor_type": "vmware",
            "username": req.headers.get("username"),
            "password": req.headers.get("password"),
            "host": host,
            "minutes": int(minutes),
            "tags": _standard_tags(req),
        }

    return await _run_monitor_handler(
        request,
        monitor_type="vmware",
        build_params=build_params,
        accept_labels=lambda params: {"host": params.get("host")},
        error_labels=lambda: {"host": request.headers.get("host")},
        log_name="VMware",
    )


@monitor_router.get("/qcloud/metrics")
async def qcloud_metrics(request):
    def build_params(req):
        minutes = req.args.get("minutes", 5)
        username = req.headers.get("username")
        logger.info("Request: Minutes=%s", minutes)
        return {
            "monitor_type": "qcloud",
            "username": username,
            "password": req.headers.get("password"),
            "minutes": int(minutes),
            "tags": _standard_tags(req),
        }

    return await _run_monitor_handler(
        request,
        monitor_type="qcloud",
        build_params=build_params,
        accept_labels=lambda params: {
            "username": _mask_credential(params.get("username") or "")
        },
        error_labels=lambda: {
            "username": _mask_credential(request.headers.get("username") or "")
        },
        log_name="QCloud",
    )


@monitor_router.get("/oceanstor/metrics")
async def oceanstor_metrics(request):
    def build_params(req):
        # Do not use the incoming HTTP Host header here. Telegraf sets it to the
        # Stargazer service address, while OceanStor collection needs the target
        # device endpoint carried in base_url.
        base_url = req.headers.get("base_url")
        host = base_url
        instance_id = req.headers.get("instance_id", "")
        logger.info("Request: Host=%s, instance_id=%s", host, instance_id)
        return {
            "monitor_type": "oceanstor",
            "username": req.headers.get("username"),
            "password": req.headers.get("password"),
            "host": host,
            "base_url": base_url,
            "instance_id": instance_id,
            "tags": _standard_tags(
                req,
                defaults={
                    "instance_type": "storage",
                    "collect_type": "oceanstor",
                    "config_type": "oceanstor",
                },
            ),
        }

    return await _run_monitor_handler(
        request,
        monitor_type="oceanstor",
        build_params=build_params,
        accept_labels=lambda params: {"host": params.get("host")},
        error_labels=lambda: {"host": request.headers.get("base_url")},
        log_name="OceanStor",
    )


@monitor_router.get("/windows/wmi/metrics")
async def windows_wmi_metrics(request):
    logger.info("event=wmi_request_received monitor_type=windows_wmi")

    host = request.headers.get("host")
    username = request.headers.get("username")
    password = request.headers.get("password")
    if not host or not username or not password:
        return _monitor_error_response(
            "windows_wmi",
            "missing required headers: host, username, password",
            status=400,
        )

    namespace = request.headers.get("namespace", "root\\cimv2")
    metrics_modules = request.headers.get(
        "metrics_modules", "cpu,mem,disk,diskio,net,processes,system"
    )
    disk_include_fstypes = request.headers.get("disk_include_fstypes", "")
    disk_exclude_fstypes = request.headers.get(
        "disk_exclude_fstypes",
        "tmpfs,devtmpfs,devfs,iso9660,overlay,aufs,squashfs,vfat,exfat,fat,fat32",
    )
    raw_timeout = request.headers.get("timeout", "60")
    try:
        timeout = int(raw_timeout)
    except (TypeError, ValueError):
        timeout = 60

    task_params = {
        "monitor_type": "windows_wmi",
        "host": host,
        "username": username,
        "password": password,
        "namespace": namespace,
        "metrics_modules": metrics_modules,
        "disk_include_fstypes": disk_include_fstypes,
        "disk_exclude_fstypes": disk_exclude_fstypes,
        "timeout": timeout,
        "tags": _standard_tags(
            request,
            defaults={
                "instance_type": "os",
                "collect_type": "http",
                "config_type": "windows_wmi",
            },
        ),
    }

    task_info = await _submit_monitor_request(request, task_params)
    logger.info(
        "event=wmi_run_accepted monitor_type=windows_wmi host=%s task_id=%s",
        host,
        task_info["task_id"],
    )
    return _monitor_accepted_response(
        "windows_wmi",
        task_info,
        host=host,
        extra_headers={"X-Monitor-Type": "windows_wmi"},
    )


@monitor_router.get("/host/metrics")
async def host_metrics(request):
    logger.info("=== Host metrics collection request received ===")

    host = request.headers.get("host")
    os_type = request.headers.get("os_type", "linux")
    username = request.headers.get("username")
    password = request.headers.get("password")
    port = request.headers.get("port", "22" if os_type == "linux" else "5986")
    metrics_modules = request.headers.get(
        "metrics_modules", "cpu,mem,disk,diskio,net,processes,system"
    )
    disk_include_fstypes = request.headers.get("disk_include_fstypes", "")
    disk_exclude_fstypes = request.headers.get(
        "disk_exclude_fstypes",
        "tmpfs,devtmpfs,devfs,iso9660,overlay,aufs,squashfs,vfat,exfat,fat,fat32",
    )
    ansible_node_id = request.headers.get("ansible_node_id", "")

    if not host or not username or not password:
        return _monitor_error_response(
            "host",
            "missing required headers: host, username, password",
            status=400,
        )
    if not ansible_node_id:
        return _monitor_error_response(
            "host",
            "missing ansible_node_id header",
            status=400,
        )

    logger.info(
        "Host metrics: host=%s, os=%s, modules=%s",
        host,
        os_type,
        metrics_modules,
    )

    def build_params(req):
        return {
            "monitor_type": "host",
            "host": host,
            "os_type": os_type,
            "username": username,
            "password": password,
            "port": port,
            "metrics_modules": metrics_modules,
            "disk_include_fstypes": disk_include_fstypes,
            "disk_exclude_fstypes": disk_exclude_fstypes,
            "ansible_node_id": ansible_node_id,
            "tags": _standard_tags(
                req,
                defaults={
                    "instance_type": "os",
                    "collect_type": "http",
                    "config_type": "host",
                },
            ),
        }

    return await _run_monitor_handler(
        request,
        monitor_type="host",
        build_params=build_params,
        accept_labels=lambda params: {"host": params.get("host")},
        error_labels=lambda: {"host": host},
        log_name="Host",
    )
