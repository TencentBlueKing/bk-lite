"""配置采集与业务监控共用的异步插件契约实现。"""

from __future__ import annotations

import importlib
import re
from typing import Any, Callable, Mapping

from core.collection_runtime import CollectionRequest
from core.target_collection_executor import (
    CollectOutcome,
    CollectOutcomeStatus,
    CollectionPlugin,
    TargetCollectionContext,
)


_AUTH_WORDS = (
    "auth",
    "password",
    "credential",
    "denied",
    "unauthorized",
    "community",
    "authkey",
    "privkey",
)
_UNREACHABLE_WORDS = (
    "tcp connect",
    "connect timed out",
    "connect failed",
    "connection refused",
    "no route",
    "host is down",
    "unreachable",
)
_SNMP_NO_RESPONSE_WORDS = (
    "no snmp response",
    "empty snmp response",
    "requesttimedout",
    "no response received before timeout",
)


class ConfigurationCollectionPlugin:
    def __init__(self, service_factory: Callable | None = None) -> None:
        self._service_factory = service_factory

    async def collect(
        self,
        target: str,
        credential: Mapping[str, Any],
        context: TargetCollectionContext,
    ) -> CollectOutcome:
        service_factory = self._service_factory
        if service_factory is None:
            from service.collection_service import CollectionService

            service_factory = CollectionService
        params = _target_params(target, credential, context)
        metrics = await service_factory(params).collect()
        error = _extract_collection_error(metrics)
        if not error:
            return CollectOutcome(
                status=CollectOutcomeStatus.SUCCESS,
                value=metrics,
            )
        return _failure_outcome(error, value=metrics)


class MonitorCollectionPlugin:
    def __init__(
        self,
        collector_factories: Mapping[str, Callable] | None = None,
    ) -> None:
        self._collector_factories = dict(collector_factories or {})

    async def collect(
        self,
        target: str,
        credential: Mapping[str, Any],
        context: TargetCollectionContext,
    ) -> CollectOutcome:
        monitor_type = str(context.params.get("monitor_type") or "")
        if monitor_type == "host":
            return await self._collect_host_remote(
                target, credential, context
            )
        factory = self._collector_factories.get(monitor_type)
        if factory is None:
            factory = _load_monitor_collector(monitor_type)
        params = _target_params(target, credential, context)
        try:
            metrics = await factory(params).collect()
        except Exception as error:  # noqa: BLE001 - 转为稳定领域错误
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
        import hashlib
        import time

        import core.host_remote_callback as callback_state
        from tasks.collectors.host_collector import HostCollector

        params = _target_params(target, credential, context)
        submitted_at = int(time.time() * 1000)
        callback_params = {
            key: params[key]
            for key in (
                "host",
                "os_type",
                "monitor_type",
                "metrics_modules",
                "disk_include_fstypes",
                "disk_exclude_fstypes",
                "tags",
                "ansible_node_id",
                "collection_task_id",
                "collection_fence",
            )
            if key in params
        }
        callback_params["callback_timestamp"] = submitted_at
        callback_caller = str(params.get("ansible_node_id") or "")
        callback_task_id = "remote-" + hashlib.sha256(
            f"{context.task_id}\0{context.plugin_ref}\0{target}\0{context.fence}".encode()
        ).hexdigest()[:24]
        callback_params["collection_result_id"] = hashlib.sha256(
            f"{context.task_id}\0{context.plugin_ref}\0{target}\0{context.fence}".encode()
        ).hexdigest()
        callback_subject = callback_state.get_host_remote_callback_subject()
        callback_payload = {
            "task_id": callback_task_id,
            "collection_task_id": context.task_id,
            "collection_fence": context.fence,
            "collection_target": target,
            "collection_plugin_ref": context.plugin_ref,
            "collection_owner": context.owner_id,
            "collection_attempt": context.fence,
            "collection_caller": callback_caller,
        }
        await callback_state.store_host_remote_callback_context(
            callback_task_id,
            callback_params,
            {
                "owner_id": context.owner_id,
                "fence": context.fence,
                "plugin_ref": context.plugin_ref,
                "target": target,
                "collection_task_id": context.task_id,
                "attempt": context.fence,
                "caller": callback_caller,
            },
        )
        accepted = await HostCollector(params).submit_collection(
            callback_task_id,
            callback_subject,
            callback_payload,
        )
        accepted_result = accepted.get("result") or {}
        if accepted.get("success") is False or accepted_result.get("accepted") is False:
            await callback_state.clear_host_remote_callback_context(
                callback_task_id
            )
            return CollectOutcome(
                status=CollectOutcomeStatus.FAILED,
                error_code="remote_submission_failed",
            )
        await callback_state.mark_host_remote_submit_accepted(callback_task_id)
        return CollectOutcome(
            status=CollectOutcomeStatus.DEFERRED,
            value={
                "callback_task_id": callback_task_id,
                "submitted_at": submitted_at,
            },
        )


class UnifiedPluginFactory:
    """只按业务插件族解析实现；运行时不感知同步/异步执行模式。"""

    def __init__(self, monitor_collector_factories=None) -> None:
        if monitor_collector_factories is None:
            monitor_collector_factories = _load_enterprise_collector_factories()
        self._monitor_collector_factories = dict(
            monitor_collector_factories or {}
        )

    def resolve(self, request: CollectionRequest) -> CollectionPlugin:
        family = str(request.params.get("plugin_family") or "configuration")
        if family == "monitor":
            return MonitorCollectionPlugin(self._monitor_collector_factories)
        if family == "configuration":
            return ConfigurationCollectionPlugin()
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
        params["host"] = target
    params["collection_task_id"] = context.task_id
    params["collection_fence"] = context.fence
    return params


def _extract_collection_error(value: Any) -> str:
    if value is None:
        return "empty collection result"
    if isinstance(value, dict):
        status = str(
            value.get("status") or value.get("collect_status") or ""
        ).lower()
        if status not in {"failed", "error"}:
            return ""
        return str(
            value.get("error")
            or value.get("collect_error")
            or value.get("cmdb_collect_error")
            or "collection failed"
        )
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
    if any(word in normalized for word in _SNMP_NO_RESPONSE_WORDS):
        status = CollectOutcomeStatus.RETRY_CREDENTIAL
        error_code = "credential_probe_no_response"
    elif any(word in normalized for word in _AUTH_WORDS):
        status = CollectOutcomeStatus.AUTH_FAILED
        error_code = "authentication_failed"
    elif any(word in normalized for word in _UNREACHABLE_WORDS):
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
