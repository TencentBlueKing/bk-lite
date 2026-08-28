"""从 plugin.yml 的 target_policy 覆盖请求预检参数。"""

from __future__ import annotations

import asyncio
from typing import Any, Mapping

from core.collection.runtime import CollectionRequest
from core.logger import logger, safe_log_value
from core.plugin.yaml_reader import PluginYamlReader, yaml_reader

# yaml mode → AsyncProtocolPreflight.preflight_kind
_MODE_TO_KIND = {
    "remote_channel": "remote",
    "outbound_only": "outbound_only",
    "tcp": "tcp",
    "tls": "https",
    "snmp": "snmp",
    "udp": "snmp",
    "cloud_endpoint": "cloud",
    "skip": "skip",
    "none": "none",
}


def apply_yaml_target_policy(
    request: CollectionRequest,
    *,
    reader: PluginYamlReader | None = None,
) -> CollectionRequest:
    """用当前 executor 对应 yaml 的 target_policy 覆盖预检参数。

    一次 run 调用一次即可；yaml 解析有缓存。
    yaml 有声明时覆盖 request_builder 兜底猜测；无声明则保留原 params。
    监控采集若已显式设置 preflight_kind（或 plugin_family=monitor），
    不得用同名 CMDB plugin.yml 的 tls/443 覆盖，否则 SNMP 存储会被 HTTPS
    预检挡死。
    """
    if str(request.params.get("plugin_family") or "") == "monitor":
        return request
    if str(request.params.get("preflight_kind") or "").strip() and request.params.get("preflight_kind_explicit"):
        return request
    plugin_name = _plugin_name(request)
    executor_type = str(request.params.get("executor_type") or "").strip()
    if not executor_type:
        executor_type = _default_executor_type(plugin_name, reader or yaml_reader)

    prefer_enterprise = _as_bool(request.params.get("prefer_enterprise"), True)
    try:
        resolved = (reader or yaml_reader).get_executor_config_with_resolution(
            plugin_name,
            executor_type,
            prefer_enterprise=prefer_enterprise,
        )
    except Exception as exc:  # noqa: BLE001 - 保留 request_builder 兜底
        logger.warning(
            "event=yaml_target_policy_unavailable task_id=%s plugin=%s " "executor=%s failed_stage=run_preparation error_type=%s",
            safe_log_value(request.task_id),
            safe_log_value(plugin_name),
            safe_log_value(executor_type),
            type(exc).__name__,
        )
        return request

    return apply_executor_target_policy(
        request,
        resolved.executor_config,
        plugin_name=plugin_name,
        executor_type=executor_type,
    )


async def apply_yaml_target_policy_async(
    request: CollectionRequest,
    *,
    reader: PluginYamlReader | None = None,
) -> CollectionRequest:
    """异步 Run 入口；通过 reader 自身的锁避免并行首次读取同一 YAML。"""
    if str(request.params.get("plugin_family") or "") == "monitor":
        return request
    if str(request.params.get("preflight_kind") or "").strip() and request.params.get("preflight_kind_explicit"):
        return request
    selected_reader = reader or yaml_reader
    plugin_name = _plugin_name(request)
    executor_type = str(request.params.get("executor_type") or "").strip()
    if not executor_type:
        executor_type = await asyncio.to_thread(
            _default_executor_type,
            plugin_name,
            selected_reader,
        )

    prefer_enterprise = _as_bool(request.params.get("prefer_enterprise"), True)
    try:
        resolved = await selected_reader.get_executor_config_with_resolution_async(
            plugin_name,
            executor_type,
            prefer_enterprise=prefer_enterprise,
        )
    except Exception as exc:  # noqa: BLE001 - 保留 request_builder 兜底
        logger.warning(
            "event=yaml_target_policy_unavailable task_id=%s plugin=%s " "executor=%s failed_stage=run_preparation error_type=%s",
            safe_log_value(request.task_id),
            safe_log_value(plugin_name),
            safe_log_value(executor_type),
            type(exc).__name__,
        )
        return request

    return apply_executor_target_policy(
        request,
        resolved.executor_config,
        plugin_name=plugin_name,
        executor_type=executor_type,
    )


def apply_executor_target_policy(
    request: CollectionRequest,
    executor_config,
    *,
    plugin_name: str | None = None,
    executor_type: str | None = None,
) -> CollectionRequest:
    """使用 fallback 后的最终执行器配置覆盖目标策略。"""

    if str(request.params.get("plugin_family") or "") == "monitor":
        return request
    if str(request.params.get("preflight_kind") or "").strip() and request.params.get("preflight_kind_explicit"):
        return request
    plugin_name = plugin_name or _plugin_name(request)
    executor_type = executor_type or str(request.params.get("executor_type") or "").strip()
    policy = (executor_config.config or {}).get("target_policy")
    if not isinstance(policy, Mapping) or not policy:
        return request

    mode = str(policy.get("mode") or "").strip().lower()
    kind = _MODE_TO_KIND.get(mode)
    if not kind:
        logger.warning(
            "event=yaml_target_policy_unknown_mode task_id=%s mode=%s " "failed_stage=run_preparation error_type=UnsupportedTargetPolicyMode",
            safe_log_value(request.task_id),
            safe_log_value(mode),
        )
        return request

    params = dict(request.params)
    params["preflight_kind"] = kind
    params["target_policy_mode"] = mode
    params["_yaml_target_policy_verified"] = True
    if "port" in policy and policy.get("port") not in (None, ""):
        params["port"] = int(policy["port"])
    if "tls" in policy:
        params.setdefault("ssl", policy["tls"])
    if kind == "cloud" and "trusted_domains" in policy:
        domains = policy.get("trusted_domains")
        if isinstance(domains, (list, tuple)):
            params["trusted_endpoint_domains"] = tuple(str(value) for value in domains)
    if not params.get("executor_type"):
        params["executor_type"] = executor_type

    _refine_pc_preflight(params, plugin_name)

    return CollectionRequest(
        task_id=request.task_id,
        plugin_ref=request.plugin_ref,
        targets=request.targets,
        credentials=request.credentials,
        params=params,
    )


def _refine_pc_preflight(params: dict[str, Any], plugin_name: str) -> None:
    """PC：Windows 拨 WinRM；macOS/其它拨 SSH remote。"""
    if plugin_name != "pc":
        return
    os_type = str(params.get("os_type") or params.get("osType") or "").strip().lower()
    if os_type in {"windows", "win", "winrm"}:
        scheme = str(params.get("winrm_scheme") or "https").strip().lower()
        params["preflight_kind"] = "tcp"
        params["port"] = 5985 if scheme == "http" else 5986
        params["ssl"] = False
        return
    params["preflight_kind"] = "remote"
    if params.get("port") in (None, ""):
        params["port"] = 22


def _plugin_name(request: CollectionRequest) -> str:
    ref = str(request.plugin_ref or "")
    if "." in ref:
        return ref.split(".", 1)[0]
    return str(request.params.get("monitor_type") or "") or str(request.params.get("model_id") or "") or str(request.params.get("plugin_name") or "")


def _default_executor_type(plugin_name: str, reader: PluginYamlReader) -> str:
    try:
        config = reader.read_plugin_config(plugin_name)
    except Exception:
        return "protocol"
    return str(config.get("default_executor") or "protocol")


def _as_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}
