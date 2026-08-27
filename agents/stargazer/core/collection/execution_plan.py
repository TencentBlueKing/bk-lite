"""把环境与插件 YAML 收敛为单次采集使用的不可变执行计划。"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from core.collection.runtime import CollectionRequest
from core.logger import logger, safe_log_value
from core.plugin.yaml_reader import ExecutorConfig, PluginYamlReader, yaml_reader

_EXECUTION_MODES = {"sync", "async", "remote"}
_CAPACITY_GROUPS = {"snmp", "sync_sdk", "remote_job", "network_topology", "default"}
_MIN_COLLECTION_TIMEOUT_SECONDS = 1.0
_MIN_SNMP_COLLECTION_TIMEOUT_SECONDS = 30.0
_MAX_COLLECTION_TIMEOUT_SECONDS = 86400.0


@dataclass(frozen=True)
class TimeoutDefaults:
    preflight_seconds: float = 15.0
    probe_seconds: float = 15.0
    collection_seconds: float = 60.0
    publish_seconds: float = 30.0

    def __post_init__(self) -> None:
        for field_name, value in vars(self).items():
            _positive_timeout(field_name, value)


@dataclass(frozen=True)
class ExecutionPlan:
    preflight_timeout_seconds: float
    probe_timeout_seconds: float
    collection_timeout_seconds: float
    publish_timeout_seconds: float
    execution_mode: str
    capacity_group: str

    def __post_init__(self) -> None:
        for field_name in (
            "preflight_timeout_seconds",
            "probe_timeout_seconds",
            "collection_timeout_seconds",
            "publish_timeout_seconds",
        ):
            _positive_timeout(field_name, getattr(self, field_name))
        if self.execution_mode not in _EXECUTION_MODES:
            raise ValueError(f"execution_mode must be one of {sorted(_EXECUTION_MODES)}")
        if self.capacity_group not in _CAPACITY_GROUPS:
            raise ValueError(f"capacity_group must be one of {sorted(_CAPACITY_GROUPS)}")


class ExecutionPlanResolver:
    """通过一个 interface 隐藏 YAML 定位、缺省与字段校验。"""

    def __init__(
        self,
        *,
        reader: PluginYamlReader | None = None,
        defaults: TimeoutDefaults | None = None,
        metrics=None,
    ) -> None:
        self._reader = reader or yaml_reader
        self._defaults = defaults or TimeoutDefaults()
        self._metrics = metrics

    def resolve(
        self,
        request: CollectionRequest,
        *,
        executor_config: ExecutorConfig | None = None,
    ) -> ExecutionPlan:
        plugin_name = _plugin_name(request)
        executor_type = str(request.params.get("executor_type") or "").strip()
        executor = executor_config
        if executor is None:
            try:
                if not executor_type:
                    plugin_config = self._reader.read_plugin_config(plugin_name)
                    executor_type = str(plugin_config.get("default_executor") or "protocol")
                resolved = self._reader.get_executor_config_with_resolution(
                    plugin_name,
                    executor_type,
                    prefer_enterprise=_as_bool(request.params.get("prefer_enterprise"), True),
                )
            except FileNotFoundError as exc:
                logger.warning(
                    "event=execution_plan_yaml_missing task_id=%s plugin=%s executor=%s "
                    "action=use_defaults failed_stage=run_preparation error_type=%s",
                    safe_log_value(request.task_id),
                    safe_log_value(plugin_name or "-"),
                    safe_log_value(executor_type or "protocol"),
                    type(exc).__name__,
                )
                return self._default_plan(executor_type or "protocol")
            executor = resolved.executor_config
        config = executor.config or {}
        target_policy = config.get("target_policy") or {}
        if not isinstance(target_policy, dict):
            target_policy = {}
        target_policy_mode = str(target_policy.get("mode") or "").strip().lower()

        execution_mode = str(config.get("execution_mode") or ("remote" if executor.is_job else "sync")).strip().lower()
        capacity_group = str(config.get("capacity_group") or ("remote_job" if executor.is_job else "default")).strip().lower()
        minimum_collection_timeout = _MIN_SNMP_COLLECTION_TIMEOUT_SECONDS if target_policy_mode == "snmp" else _MIN_COLLECTION_TIMEOUT_SECONDS
        raw_collection_timeout = request.params.get("timeout")
        requested_collection_timeout = _task_collection_timeout_candidate(
            raw_collection_timeout,
            self._defaults.collection_seconds,
        )
        collection_timeout = _task_collection_timeout(
            raw_collection_timeout,
            self._defaults.collection_seconds,
            minimum=minimum_collection_timeout,
        )
        timeout_was_clamped = target_policy_mode == "snmp" and requested_collection_timeout < minimum_collection_timeout
        if timeout_was_clamped:
            if self._metrics is not None:
                self._metrics.increment("snmp_timeout_clamped_total")
            logger.warning(
                "event=snmp_collection_timeout_clamped task_id=%s plugin=%s "
                "configured_seconds=%s effective_seconds=%s "
                "failed_stage=run_preparation error_type=CollectionTimeoutClamped",
                safe_log_value(request.task_id),
                safe_log_value(plugin_name or "-"),
                requested_collection_timeout,
                collection_timeout,
            )
        return ExecutionPlan(
            preflight_timeout_seconds=_configured_timeout(
                target_policy,
                "timeout",
                self._defaults.preflight_seconds,
                "preflight_timeout_seconds",
            ),
            probe_timeout_seconds=_configured_timeout(
                config,
                "probe_timeout",
                self._defaults.probe_seconds,
                "probe_timeout_seconds",
            ),
            collection_timeout_seconds=collection_timeout,
            publish_timeout_seconds=self._defaults.publish_seconds,
            execution_mode=execution_mode,
            capacity_group=capacity_group,
        )

    def _default_plan(self, executor_type: str) -> ExecutionPlan:
        is_remote = executor_type == "job"
        return ExecutionPlan(
            preflight_timeout_seconds=self._defaults.preflight_seconds,
            probe_timeout_seconds=self._defaults.probe_seconds,
            collection_timeout_seconds=self._defaults.collection_seconds,
            publish_timeout_seconds=self._defaults.publish_seconds,
            execution_mode="remote" if is_remote else "sync",
            capacity_group="remote_job" if is_remote else "default",
        )


def _configured_timeout(
    config: dict[str, Any],
    key: str,
    default: float,
    field_name: str,
) -> float:
    value = default if key not in config else config[key]
    return _positive_timeout(field_name, value)


def _task_collection_timeout(
    raw_value: Any,
    default: float,
    *,
    minimum: float = _MIN_COLLECTION_TIMEOUT_SECONDS,
) -> float:
    """单对象采集预算：表单 timeout → 钳制 1s～86400s；空/0 回落环境默认。"""
    timeout = _task_collection_timeout_candidate(raw_value, default)
    clamped = min(
        _MAX_COLLECTION_TIMEOUT_SECONDS,
        max(minimum, timeout),
    )
    return _positive_timeout("collection_timeout_seconds", clamped)


def _task_collection_timeout_candidate(raw_value: Any, default: float) -> float:
    if raw_value is None:
        return _positive_timeout("collection_timeout_seconds", default)
    if isinstance(raw_value, str) and not raw_value.strip():
        return _positive_timeout("collection_timeout_seconds", default)
    try:
        timeout = float(raw_value)
    except (TypeError, ValueError):
        return _positive_timeout("collection_timeout_seconds", default)
    if not math.isfinite(timeout) or timeout <= 0:
        return _positive_timeout("collection_timeout_seconds", default)
    return timeout


def _positive_timeout(field_name: str, value: Any) -> float:
    try:
        timeout = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a positive finite number") from exc
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError(f"{field_name} must be a positive finite number")
    return timeout


def _plugin_name(request: CollectionRequest) -> str:
    plugin_ref = str(request.plugin_ref or "")
    if "." in plugin_ref:
        return plugin_ref.split(".", 1)[0]
    return str(request.params.get("monitor_type") or "") or str(request.params.get("model_id") or "") or str(request.params.get("plugin_name") or "")


def _as_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}
