"""配置采集与业务监控共用的异步插件契约实现。"""

from __future__ import annotations

import asyncio
import importlib
import re
from typing import Any, Callable, Mapping

from core.collection.constants import AUTH_ERROR_WORDS, SNMP_NO_RESPONSE_WORDS, UNREACHABLE_ERROR_WORDS
from core.collection.contracts import (
    AccessProbeResult,
    AccessProbeStatus,
    CollectionPlugin,
    CollectOutcome,
    CollectOutcomeStatus,
    StructuredMetricsPayload,
    TargetCollectionContext,
)
from core.collection.node_info_lookup import RunNodeInfoLookup
from core.collection.runtime import CollectionRequest
from core.logger import logger, safe_log_value
from core.plugin.error_logging import log_plugin_exception, should_log_plugin_exception


class ConfigurationCollectionPlugin:
    """配置采集插件；supports_access_probe 默认开启，无 probe 时返回 NOT_SUPPORTED。"""

    supports_access_probe = True

    def __init__(
        self,
        service_factory: Callable | None = None,
        *,
        node_info_lookup=None,
        metrics=None,
    ) -> None:
        if service_factory is None:
            raise ValueError("configuration plugin requires service_factory " "(inject at composition root; core must not import service)")
        self._service_factory = service_factory
        self._node_info_lookup = node_info_lookup
        self._metrics = metrics
        self._prepared = False
        self._prepared_executor_config = None

    @property
    def prepared_executor_config(self):
        return self._prepared_executor_config

    async def prepare(self, request: CollectionRequest) -> None:
        """Run 生命周期准备：目标入队前解析静态 Service 执行计划。"""
        if self._prepared:
            return
        prepare_factory = getattr(self._service_factory, "prepare", None)
        if callable(prepare_factory):
            try:
                self._service_factory = await prepare_factory(dict(request.params))
                self._prepared_executor_config = getattr(
                    self._service_factory,
                    "executor_config",
                    None,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - 保持目标级历史错误结果语义
                if self._metrics is not None:
                    self._metrics.increment("run_preparation_fallback_total")
                logger.warning(
                    "event=collection_run_preparation_fallback task_id=%s " "plugin_ref=%s failed_stage=run_preparation error_type=%s",
                    safe_log_value(request.task_id),
                    safe_log_value(request.plugin_ref),
                    type(exc).__name__,
                )
        self._prepared = True

    async def probe(
        self,
        target: str,
        credential: Mapping[str, Any],
        context: TargetCollectionContext,
        *,
        timeout_seconds: float,
    ) -> AccessProbeResult:
        params = _target_params(target, credential, context)
        if self._metrics is not None:
            params["_runtime_metrics"] = self._metrics
        await self._prepare_job_params(target, params)
        try:
            configured_timeout = float(params.get("timeout", timeout_seconds))
        except (TypeError, ValueError):
            configured_timeout = timeout_seconds
        params["timeout"] = min(configured_timeout, timeout_seconds)
        return await self._service_factory(params).probe()

    async def collect(
        self,
        target: str,
        credential: Mapping[str, Any],
        context: TargetCollectionContext,
    ) -> CollectOutcome:
        params = _target_params(target, credential, context)
        if self._metrics is not None:
            params["_runtime_metrics"] = self._metrics
        await self._prepare_job_params(target, params)
        params["_runtime_structured_metrics"] = True
        metrics = await self._service_factory(params).collect()
        error = _extract_collection_error(metrics)
        if not error:
            return CollectOutcome(
                status=CollectOutcomeStatus.SUCCESS,
                value=metrics,
            )
        return _failure_outcome(error, value=metrics)

    async def close(self) -> None:
        if self._node_info_lookup is not None:
            await self._node_info_lookup.close()

    async def _prepare_job_params(self, target: str, params: dict[str, Any]) -> None:
        params.pop("node_info", None)
        if str(params.get("executor_type") or "").lower() != "job":
            return
        if self._node_info_lookup is None:
            return
        connect_host = str(params.get("connect_ip") or params.get("host") or "")
        node_info = await self._node_info_lookup.get(
            target,
            connect_host=connect_host,
        )
        if node_info:
            params["node_info"] = dict(node_info)


class MonitorCollectionPlugin:
    """业务监控插件；host remote 不做假 AccessProbe，由 Responder 回调裁决。"""

    supports_access_probe = True

    def __init__(
        self,
        collector_factories: Mapping[str, Callable] | None = None,
    ) -> None:
        self._collector_factories = dict(collector_factories or {})

    async def probe(
        self,
        target: str,
        credential: Mapping[str, Any],
        context: TargetCollectionContext,
        *,
        timeout_seconds: float,
    ) -> AccessProbeResult:
        monitor_type = str(context.params.get("monitor_type") or "")
        if monitor_type == "host":
            # 到目标 SSH Attempt 由 Responder 负责；此处不伪造 UNKNOWN→采集
            return AccessProbeResult(status=AccessProbeStatus.NOT_SUPPORTED)
        factory = self._collector_factories.get(monitor_type)
        if factory is None:
            factory = _load_monitor_collector(monitor_type)
        params = _target_params(target, credential, context)
        try:
            configured_timeout = float(params.get("timeout", timeout_seconds))
        except (TypeError, ValueError):
            configured_timeout = timeout_seconds
        params["timeout"] = min(configured_timeout, timeout_seconds)
        collector = factory(params)
        probe = getattr(collector, "probe", None)
        if probe is None:
            return AccessProbeResult(status=AccessProbeStatus.NOT_SUPPORTED)
        result = await probe()
        if not isinstance(result, AccessProbeResult):
            raise TypeError("monitor probe must return AccessProbeResult")
        return result

    async def collect(
        self,
        target: str,
        credential: Mapping[str, Any],
        context: TargetCollectionContext,
    ) -> CollectOutcome:
        monitor_type = str(context.params.get("monitor_type") or "")
        if monitor_type == "host":
            return await self._collect_host_remote(target, credential, context)
        factory = self._collector_factories.get(monitor_type)
        if factory is None:
            factory = _load_monitor_collector(monitor_type)
        params = _target_params(target, credential, context)
        try:
            metrics = await factory(params).collect()
        except Exception as error:  # noqa: BLE001 - 转为稳定领域错误
            if should_log_plugin_exception(context.params):
                log_plugin_exception(
                    logger,
                    error=error,
                    task_id=context.task_id,
                    plugin_ref=context.plugin_ref,
                    model_id=context.params.get("model_id"),
                    plugin_name=monitor_type,
                    target=target,
                )
            return _failure_outcome(str(error))
        if not metrics:
            return CollectOutcome(
                status=CollectOutcomeStatus.FAILED,
                error_code="empty_collection_result",
            )
        return CollectOutcome(
            status=CollectOutcomeStatus.SUCCESS,
            value=metrics,
        )

    @staticmethod
    async def _collect_host_remote(
        target: str,
        credential: Mapping[str, Any],
        context: TargetCollectionContext,
    ) -> CollectOutcome:
        from core.collection.host_remote.adapter import submit_host_remote_collection

        params = _target_params(target, credential, context)
        return await submit_host_remote_collection(target, credential, context, params=params)


class UnifiedPluginFactory:
    """只按业务插件族解析实现；运行时不感知同步/异步执行模式。"""

    def __init__(
        self,
        monitor_collector_factories=None,
        configuration_service_factory: Callable | None = None,
        configuration_node_info_loader: Callable | None = None,
        metrics=None,
    ) -> None:
        if monitor_collector_factories is None:
            monitor_collector_factories = _load_enterprise_collector_factories()
        self._monitor_collector_factories = dict(monitor_collector_factories or {})
        self._configuration_service_factory = configuration_service_factory
        self._configuration_node_info_loader = configuration_node_info_loader
        self._metrics = metrics

    def resolve(self, request: CollectionRequest) -> CollectionPlugin:
        family = str(request.params.get("plugin_family") or "configuration")
        if family == "monitor":
            return MonitorCollectionPlugin(self._monitor_collector_factories)
        if family == "configuration":
            node_info_lookup = None
            if (
                self._configuration_node_info_loader is not None
                and str(request.params.get("executor_type") or "").lower() == "job"
                and not request.params.get("target_is_logical")
                and request.params.get("collect_task_id") not in (None, "")
            ):
                node_info_lookup = RunNodeInfoLookup(
                    task_id=request.task_id,
                    targets=request.targets,
                    loader=self._configuration_node_info_loader,
                    metrics=self._metrics,
                    collect_task_id=request.params.get("collect_task_id"),
                    cloud_region_id=request.params.get("cloud_region_id"),
                )
            return ConfigurationCollectionPlugin(
                self._configuration_service_factory,
                node_info_lookup=node_info_lookup,
                metrics=self._metrics,
            )
        raise ValueError(f"unsupported plugin_family: {family}")


def _load_enterprise_collector_factories() -> Mapping[str, Callable]:
    """可选企业包必须注册 Collector 工厂，不能注册自行发布的 handler。"""
    try:
        module = importlib.import_module("enterprise.stargazer_collectors")
    except ImportError:
        return {}
    factories = module.get_monitor_collector_factories()
    if not isinstance(factories, Mapping):
        raise TypeError("enterprise collector registry must return a mapping")
    return factories


def _target_params(
    target: str,
    credential: Mapping[str, Any],
    context: TargetCollectionContext,
) -> dict[str, Any]:
    params = dict(context.params)
    params.pop("hosts", None)
    params.pop("targets", None)
    params.pop("credentials_pool", None)
    params.update(dict(credential))
    if not params.pop("target_is_logical", False):
        params["host"] = params.pop("_validated_connect_host", "") or target
        params.setdefault("target_hostname", target)
    params["collection_task_id"] = context.task_id
    params["collection_plugin_ref"] = context.plugin_ref
    params["collection_fence"] = context.fence
    return params


def _extract_collection_error(value: Any) -> str:
    if isinstance(value, StructuredMetricsPayload):
        return value.error
    if value is None:
        return "empty collection result"
    if isinstance(value, dict):
        status = str(value.get("status") or value.get("collect_status") or "").lower()
        if status not in {"failed", "error"}:
            return ""
        return str(value.get("error") or value.get("collect_error") or value.get("cmdb_collect_error") or "collection failed")
    text = str(value)
    if not any(
        marker in text
        for marker in (
            'collect_status="failed"',
            'collect_status="error"',
            'status="error"',
            "cmdb_collect_error",
        )
    ):
        return ""
    match = re.search(r'collect_error="((?:[^"\\]|\\.)*)"', text)
    if match:
        return match.group(1).replace('\\"', '"').replace("\\\\", "\\")
    return "collection failed"


def _failure_outcome(error: str, *, value: Any = None) -> CollectOutcome:
    normalized = str(error or "").lower()
    if "tls validation failed" in normalized:
        status = CollectOutcomeStatus.UNREACHABLE
        error_code = "tls_validation_failed"
    elif "product/api mismatch" in normalized:
        status = CollectOutcomeStatus.FAILED
        error_code = "product_api_mismatch"
    elif any(word in normalized for word in SNMP_NO_RESPONSE_WORDS):
        status = CollectOutcomeStatus.RETRY_CREDENTIAL
        error_code = "credential_probe_no_response"
    elif any(word in normalized for word in AUTH_ERROR_WORDS):
        status = CollectOutcomeStatus.AUTH_FAILED
        error_code = "authentication_failed"
    elif any(word in normalized for word in UNREACHABLE_ERROR_WORDS):
        status = CollectOutcomeStatus.UNREACHABLE
        error_code = "target_unreachable"
    else:
        status = CollectOutcomeStatus.FAILED
        error_code = "collection_failed"
    return CollectOutcome(
        status=status,
        value=value,
        error_code=error_code,
        detail=type(error).__name__ if isinstance(error, Exception) else "",
    )


def _load_monitor_collector(monitor_type: str):
    if monitor_type == "vmware":
        from tasks.collectors.vmware_collector import VmwareCollector

        return VmwareCollector
    if monitor_type == "qcloud":
        from tasks.collectors.qcloud_collector import QCloudCollector

        return QCloudCollector
    if monitor_type == "oceanstor":
        from tasks.collectors.oceanstor_collector import OceanStorCollector

        return OceanStorCollector
    if monitor_type == "windows_wmi":
        from tasks.collectors.host_wmi_collector import WindowsWmiCollector

        return WindowsWmiCollector
    if monitor_type == "host":
        from tasks.collectors.host_collector import HostCollector

        return HostCollector
    raise ValueError(f"unsupported monitor_type: {monitor_type}")
