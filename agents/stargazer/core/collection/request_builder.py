"""把 HTTP 参数规范化为一个多目标 CollectionRequest。"""

from __future__ import annotations

import base64
import json
import os
from typing import Any, Mapping, Sequence

from core.collection.constants import CLOUD_TYPES, CREDENTIAL_KEYS, DEFAULT_PORTS, FLATTENED_CREDENTIAL_KEY
from core.collection.enums import WorkloadClass
from core.collection.runtime import CollectionRequest
from core.logger import logger


def parse_flattened_credentials_pool(
    params: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """从平铺 header（credential_N_*）还原凭据池。"""
    if not isinstance(params, Mapping) or not params:
        return []

    raw_count = params.get("credential_count")
    try:
        credential_count = int(raw_count)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        credential_count = 0

    grouped_credentials: dict[int, dict[str, Any]] = {}
    for key, value in params.items():
        match = FLATTENED_CREDENTIAL_KEY.match(str(key))
        if not match:
            continue
        index = int(match.group(1))
        field_name = match.group(2)
        grouped_credentials.setdefault(index, {})[field_name] = value

    if not grouped_credentials:
        return []

    if credential_count <= 0:
        credential_count = max(grouped_credentials) + 1

    credentials_pool: list[dict[str, Any]] = []
    for index in range(credential_count):
        credential = grouped_credentials.get(index)
        if isinstance(credential, dict) and credential:
            credentials_pool.append(credential)
    return credentials_pool


def parse_credentials_pool(raw_value: Any = None, params: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    """优先平铺 header，其次 JSON/base64 列表。"""
    flattened_pool = parse_flattened_credentials_pool(params)
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
                logger.warning("Failed to parse credentials_pool payload, " "fallback to single credential mode")
                return []

    if not isinstance(credentials_pool, list):
        return []

    return [item for item in credentials_pool if isinstance(item, dict)]


def build_collection_request(
    *,
    task_id: str,
    params: Mapping[str, Any],
    workload_class: WorkloadClass = WorkloadClass.CONFIGURATION,
) -> CollectionRequest:
    normalized_task_id = str(task_id or "").strip()
    if not normalized_task_id:
        raise ValueError("task_id is required")
    source = dict(params or {})
    monitor_type = str(source.get("monitor_type") or "").strip()
    model_id = str(source.get("model_id") or "").strip()
    family = "monitor" if monitor_type else "configuration"
    plugin_name = monitor_type or model_id or str(source.get("plugin_name") or "")
    if not plugin_name:
        raise ValueError("monitor_type or model_id is required")

    max_targets = int(os.getenv("MAX_TARGETS_PER_RUN", "10000"))
    raw_targets = source.get("targets", source.get("hosts"))
    if isinstance(raw_targets, Sequence) and not isinstance(raw_targets, (str, bytes, bytearray)) and len(raw_targets) > max_targets:
        raise ValueError(f"target count {len(raw_targets)} exceeds MAX_TARGETS_PER_RUN={max_targets}")
    if isinstance(raw_targets, str) and raw_targets.count(",") + 1 > max_targets:
        raise ValueError("target count exceeds MAX_TARGETS_PER_RUN")
    targets, logical_target = _targets(source, plugin_name)
    if len(targets) > max_targets:
        raise ValueError(f"target count {len(targets)} exceeds MAX_TARGETS_PER_RUN={max_targets}")
    credentials = _credentials(source)
    max_credentials = int(os.getenv("MAX_CREDENTIALS_PER_RUN", "100"))
    if len(credentials) > max_credentials:
        raise ValueError(f"credential count {len(credentials)} exceeds MAX_CREDENTIALS_PER_RUN={max_credentials}")
    public_params = {
        key: value
        for key, value in source.items()
        if key not in CREDENTIAL_KEYS
        and key not in {"credentials_pool", "hosts", "targets"}
        and key != "credential_count"
        and key
        not in {
            "target_is_logical",
            "target_policy_mode",
            "trusted_endpoint_domains",
            "_yaml_target_policy_verified",
            "_validated_connect_host",
        }
        and not FLATTENED_CREDENTIAL_KEY.fullmatch(str(key))
    }
    public_params["plugin_family"] = family
    # 空字符串同样要规范化；否则会让不同任务意外共享 default 之外的空 scope。
    public_params["scope_id"] = str(source.get("scope_id") or source.get("collect_task_id") or "default")
    public_params["credential_set_version"] = str(source.get("credential_set_version") or "default")
    public_params["target_is_logical"] = logical_target
    _apply_preflight_defaults(public_params, plugin_name, family)

    return CollectionRequest(
        task_id=normalized_task_id,
        plugin_ref=f"{plugin_name}.{'monitor' if monitor_type else 'config'}",
        targets=targets,
        credentials=credentials,
        params=public_params,
        workload_class=workload_class,
    )


def _targets(source: dict[str, Any], plugin_name: str) -> tuple[tuple[str, ...], bool]:
    raw_targets = source.get("targets", source.get("hosts"))
    if isinstance(raw_targets, str):
        raw_targets = [item.strip() for item in raw_targets.split(",")]
    if isinstance(raw_targets, Sequence) and not isinstance(raw_targets, (str, bytes, bytearray)):
        targets = tuple(dict.fromkeys(str(item).strip() for item in raw_targets if str(item).strip()))
        if targets:
            return targets, False
    host = str(source.get("host") or source.get("hostname") or source.get("base_url") or "").strip()
    if host:
        return (host,), False
    logical = str((source.get("tags") or {}).get("instance_id") or source.get("instance_id") or plugin_name)
    return (logical,), True


def _credentials(source: dict[str, Any]) -> tuple[Mapping[str, Any], ...]:
    credentials = parse_credentials_pool(source.get("credentials_pool"), params=source)
    if not credentials:
        credential = {key: source[key] for key in CREDENTIAL_KEYS if key in source}
        credentials = [credential] if credential else [{}]
    for index, credential in enumerate(credentials, 1):
        credential.setdefault("credential_id", f"credential-{index}")
    return tuple(credentials)


def _apply_preflight_defaults(params: dict[str, Any], plugin_name: str, family: str) -> None:
    if params.get("preflight_kind"):
        return
    if plugin_name in CLOUD_TYPES:
        params["preflight_kind"] = "cloud"
        return
    if plugin_name in {"network", "network_topo", "security_device", "tape_library"}:
        params["preflight_kind"] = "snmp"
        params.setdefault("port", 161)
        return
    if plugin_name == "pc":
        os_type = str(params.get("os_type") or params.get("osType") or "").strip().lower()
        if os_type in {"windows", "win", "winrm"}:
            scheme = str(params.get("winrm_scheme") or "https").strip().lower()
            params["preflight_kind"] = "tcp"
            params["port"] = 5985 if scheme == "http" else 5986
            params["ssl"] = False
        else:
            params["preflight_kind"] = "remote"
            params.setdefault("port", 22)
        return
    if plugin_name in {"host", "network_config_file"}:
        params["preflight_kind"] = "remote"
        params.setdefault("port", 22)
        return
    if family == "configuration" and str(params.get("executor_type") or "").lower() == "job" and not params.get("target_is_logical"):
        params["preflight_kind"] = "remote"
        return
    if params.get("base_url"):
        params["preflight_kind"] = "https"
        return
    port = params.get("port") or DEFAULT_PORTS.get(plugin_name)
    if port:
        params["port"] = int(port)
        params["preflight_kind"] = "tcp"
    else:
        params["preflight_kind"] = "none"
