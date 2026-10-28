from __future__ import annotations

from typing import Any, Mapping, Sequence

_JOB_TARGET_TYPES = frozenset(
    {
        "nginx",
        "tomcat",
        "kafka",
        "zookeeper",
        "rabbitmq",
        "consul",
        "etcd",
        "host",
        "apache",
        "openresty",
        "memcached",
        "minio",
        "haproxy",
        "iis",
        "activemq",
        "rocketmq",
        "squid",
    }
)
_SNAPSHOT_KEYS = (
    "version",
    "db_version",
    "bin_path",
    "conf_path",
    "config_path",
    "install_path",
    "nginx_path",
    "log_path",
    "hostname",
    "os_type",
    "os_name",
    "os_version",
    "os_bit",
    "cpu_arch",
    "cpu_model",
    "cpu_core",
    "memory",
    "disk",
    "inner_mac",
    "inst_name",
)


async def collect_scan_plugin(
    hit: Mapping[str, Any],
    pool: Sequence[Mapping[str, Any]],
    *,
    host_login: Mapping[str, Any] | None = None,
    collect_task_id: Any = None,
) -> dict[str, Any]:
    """对已有命中复用现有 `*_info` 插件；由 SCAN 编排调用，不走 collect_info 接纳。"""
    target_type = str(hit.get("target_type") or "").strip()
    host = str(hit.get("host") or "").strip()
    port = int(hit.get("port") or 0)
    if not target_type or not host or not pool:
        return {"success": False, "error_code": "collect_skipped", "snapshot": {"host": host, "port": port}}

    credential = dict(pool[0] or {})
    if credential.get("username") and not credential.get("user"):
        credential["user"] = credential.get("username")
    params: dict[str, Any] = {
        "model_id": target_type,
        "plugin_name": f"{target_type}_info",
        "host": host,
        "port": port,
        "executor_type": "job" if target_type in _JOB_TARGET_TYPES else "protocol",
        "_runtime_structured_metrics": True,
        **credential,
    }
    task_id = collect_task_id if collect_task_id not in (None, "") else (host_login or {}).get("execution_id")
    if task_id not in (None, ""):
        params["collect_task_id"] = task_id
    cloud_region = (host_login or {}).get("cloud_region")
    if isinstance(cloud_region, dict) and cloud_region:
        params["cloud_region"] = cloud_region
        if cloud_region.get("id") not in (None, ""):
            params["cloud_region_id"] = cloud_region.get("id")

    from service.collection_service import CollectionService

    service = CollectionService(params)
    metrics = await service.collect()
    error = str(getattr(metrics, "error", "") or "")
    if not error and isinstance(metrics, dict):
        error = str(metrics.get("error") or "")
        if metrics.get("status") == "failed" and not error:
            error = "collect_failed"
    if error:
        return {
            "success": False,
            "error_code": "collect_failed",
            "snapshot": {"host": host, "port": port},
        }
    data = getattr(metrics, "data", metrics)
    return {"success": True, "snapshot": _snapshot_from_metrics(host, port, data)}


def _snapshot_from_metrics(host: str, port: int, data: Any) -> dict[str, Any]:
    snapshot = {"host": host, "port": port}
    if not isinstance(data, dict):
        return snapshot
    _copy_keys(snapshot, data)
    for value in data.values():
        if isinstance(value, list) and value and isinstance(value[0], dict):
            _copy_keys(snapshot, value[0])
            break
        if isinstance(value, dict):
            _copy_keys(snapshot, value)
    return snapshot


def _copy_keys(snapshot: dict[str, Any], source: Mapping[str, Any]) -> None:
    for key in _SNAPSHOT_KEYS:
        value = source.get(key)
        if value not in (None, ""):
            snapshot[key] = value
