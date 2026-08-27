"""凭据尝试中的带预算协议操作。"""

from __future__ import annotations

import asyncio
import time

from core.collection.contracts import (
    AccessProbe,
    AccessProbeResult,
    AccessProbeStatus,
    CollectionPlugin,
    CollectOutcome,
    CollectOutcomeStatus,
    TargetCollectionContext,
    TargetCollectionResult,
)
from core.collection.enums import FailureStage
from core.collection.execution_plan import ExecutionPlan
from core.collection.metrics import CollectionMetrics
from core.logger import logger
from core.plugin.error_logging import log_plugin_exception, should_log_plugin_exception


class CredentialOperationRunner:
    """执行 access probe 与正式 collect，并持有各自独立预算。"""

    def __init__(
        self,
        *,
        access_probe: AccessProbe | None,
        plugin: CollectionPlugin,
        plan: ExecutionPlan,
        metrics: CollectionMetrics,
    ) -> None:
        self._access_probe = access_probe
        self._plugin = plugin
        self._plan = plan
        self._metrics = metrics

    async def run_access_probe(
        self,
        target: str,
        credential,
        context: TargetCollectionContext,
        attempts: int,
        *,
        enabled: bool,
        target_started_at: float,
    ) -> AccessProbeResult | TargetCollectionResult:
        if not enabled or self._access_probe is None:
            return AccessProbeResult(status=AccessProbeStatus.NOT_SUPPORTED)

        access_probe_started = time.monotonic()
        self._metrics.observe(
            "target_started_to_probe_seconds",
            access_probe_started - target_started_at,
        )
        try:
            async with asyncio.timeout(self._plan.probe_timeout_seconds):
                return await self._access_probe.probe(
                    target,
                    credential,
                    context,
                    timeout_seconds=self._plan.probe_timeout_seconds,
                )
        except TimeoutError:
            self._metrics.observe(
                "timeout_overshoot_seconds",
                max(
                    0.0,
                    time.monotonic() - access_probe_started - self._plan.probe_timeout_seconds,
                ),
            )
            self._metrics.increment("access_probe_timeout_total")
            self._metrics.increment("probe_timeout_total")
            return AccessProbeResult(
                status=AccessProbeStatus.NO_RESPONSE,
                error_code="access_probe_timeout",
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - 不把 Adapter 异常正文写入结果
            self._metrics.increment("access_probe_error_total")
            credential_id = str(credential.get("credential_id") or "")
            if should_log_plugin_exception(context.params):
                log_plugin_exception(
                    logger,
                    error=exc,
                    task_id=context.task_id,
                    plugin_ref=context.plugin_ref,
                    model_id=context.params.get("model_id"),
                    plugin_name=context.params.get("plugin_name"),
                    target=target,
                )
            return TargetCollectionResult(
                target=target,
                status="failed",
                attempts=attempts,
                credential_id=credential_id,
                error_code="access_probe_error",
                failed_stage=FailureStage.ACCESS_PROBE,
            )
        finally:
            duration = time.monotonic() - access_probe_started
            self._metrics.increment("access_probe_duration_seconds_total", duration)
            self._metrics.observe("access_probe_duration_seconds", duration)
            self._metrics.increment("access_probe_total")

    async def run_collect(
        self,
        target: str,
        credential,
        context: TargetCollectionContext,
        *,
        target_started_at: float,
    ) -> CollectOutcome:
        plugin_started = time.monotonic()
        self._metrics.observe(
            "target_started_to_collect_seconds",
            plugin_started - target_started_at,
        )
        mode = self._plan.execution_mode
        group = self._plan.capacity_group
        self._metrics.increment(f"execution_mode_{mode}_total")
        self._metrics.increment(f"capacity_group_{group}_total")
        if mode == "sync":
            self._metrics.add_gauge("sync_calls_in_flight", 1)
        try:
            async with asyncio.timeout(self._plan.collection_timeout_seconds):
                return await self._plugin.collect(target, credential, context)
        except TimeoutError:
            self._metrics.observe(
                "timeout_overshoot_seconds",
                max(
                    0.0,
                    time.monotonic() - plugin_started - self._plan.collection_timeout_seconds,
                ),
            )
            self._metrics.increment("plugin_timeout_total")
            self._metrics.increment("collection_timeout_total")
            self._metrics.increment(f"execution_mode_{mode}_timeout_total")
            self._metrics.increment(f"capacity_group_{group}_timeout_total")
            return CollectOutcome(
                status=CollectOutcomeStatus.FAILED,
                error_code="plugin_timeout",
            )
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001 - 收敛插件异常为稳定结果
            if should_log_plugin_exception(context.params):
                log_plugin_exception(
                    logger,
                    error=error,
                    task_id=context.task_id,
                    plugin_ref=context.plugin_ref,
                    model_id=context.params.get("model_id"),
                    plugin_name=context.params.get("plugin_name"),
                    target=target,
                )
            return CollectOutcome(
                status=CollectOutcomeStatus.FAILED,
                error_code="plugin_error",
                detail=type(error).__name__,
            )
        finally:
            if mode == "sync":
                self._metrics.add_gauge("sync_calls_in_flight", -1)
            duration = time.monotonic() - plugin_started
            self._metrics.increment("plugin_duration_seconds_total", duration)
            self._metrics.observe("plugin_duration_seconds", duration)
            self._metrics.observe(f"execution_mode_{mode}_duration_seconds", duration)
            self._metrics.observe(f"capacity_group_{group}_duration_seconds", duration)
            self._metrics.increment("plugin_total")
