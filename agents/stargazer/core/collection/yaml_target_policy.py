"""从 plugin.yml 的 target_policy 覆盖请求预检参数。"""

from __future__ import annotations

from typing import Any, Mapping

from core.collection.runtime import CollectionRequest
from core.logger import logger
from core.plugin.yaml_reader import PluginYamlReader, yaml_reader

# yaml mode → AsyncProtocolPreflight.preflight_kind
_MODE_TO_KIND = {
    "remote_channel": "remote",
    "outbound_only": "outbound_only",
    "tcp": "tcp",
    "tls": "https",
    "cloud_endpoint": "cloud",
    "skip": "skip",
}


def apply_yaml_target_policy(
    request: CollectionRequest,
    *,
    reader: PluginYamlReader | None = None,
) -> CollectionRequest:
    """用当前 executor 对应 yaml 的 target_policy 覆盖预检参数。

    一次 run 调用一次即可；yaml 解析有缓存。
    yaml 有声明时覆盖 request_builder 兜底猜测；无声明则保留原 params。
    """
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
            "event=yaml_target_policy_unavailable task_id=%s plugin=%s "
            "executor=%s error_type=%s",
            request.task_id,
            plugin_name,
            executor_type,
            type(exc).__name__,
        )
        return request

    policy = (resolved.executor_config.config or {}).get("target_policy")
    if not isinstance(policy, Mapping) or not policy:
        return request

    mode = str(policy.get("mode") or "").strip().lower()
    kind = _MODE_TO_KIND.get(mode)
    if not kind:
        logger.warning(
            "event=yaml_target_policy_unknown_mode task_id=%s mode=%s",
            request.task_id,
            mode,
        )
        return request

    params = dict(request.params)
    params["preflight_kind"] = kind
    params["target_policy_mode"] = mode
    if "port" in policy and policy.get("port") not in (None, ""):
        params["port"] = int(policy["port"])
    if "tls" in policy:
        params.setdefault("ssl", policy["tls"])
    if not params.get("executor_type"):
        params["executor_type"] = executor_type

    return CollectionRequest(
        task_id=request.task_id,
        plugin_ref=request.plugin_ref,
        targets=request.targets,
        credentials=request.credentials,
        params=params,
    )


def _plugin_name(request: CollectionRequest) -> str:
    ref = str(request.plugin_ref or "")
    if "." in ref:
        return ref.split(".", 1)[0]
    return (
        str(request.params.get("monitor_type") or "")
        or str(request.params.get("model_id") or "")
        or str(request.params.get("plugin_name") or "")
    )


def _default_executor_type(
    plugin_name: str, reader: PluginYamlReader
) -> str:
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
