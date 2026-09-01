"""单目标采集尝试：安全策略、凭据轮换、可选探测与正式采集。"""

from __future__ import annotations

import asyncio
import time

from core.collection.contracts import (
    AccessProbe,
    CollectionPlugin,
    PreflightProbe,
    PreflightResult,
    PreflightStatus,
    TargetCollectionContext,
    TargetCollectionResult,
    TargetExecutorSettings,
)
from core.collection.credential_attempt import CredentialAttemptRunner
from core.collection.credential_policy import CredentialPolicy
from core.collection.enums import FailureStage
from core.collection.execution_plan import ExecutionPlan
from core.collection.metrics import CollectionMetrics
from core.collection.runtime import CollectionRequest, RunLease
from core.infra.redis_client import is_credential_state_redis_error
from core.logger import logger, safe_log_value
from core.plugin.error_logging import PluginExceptionLogBudget


class TargetAttemptRunner:
    """通过一个 run interface 隐藏单目标的全部采集前置与凭据尝试。"""

    def __init__(
        self,
        *,
        preflight: PreflightProbe,
        access_probe: AccessProbe | None,
        plugin: CollectionPlugin,
        credential_policy: CredentialPolicy,
        settings: TargetExecutorSettings,
        plan: ExecutionPlan,
        metrics: CollectionMetrics,
    ) -> None:
        self._preflight = preflight
        self._credential_policy = credential_policy
        self._plan = plan
        self._metrics = metrics
        self._credential_attempt_runner = CredentialAttemptRunner(
            access_probe=access_probe,
            plugin=plugin,
            credential_policy=credential_policy,
            settings=settings,
            plan=plan,
            metrics=metrics,
        )

    async def run(
        self,
        request: CollectionRequest,
        target: str,
        lease: RunLease,
        *,
        plugin_exception_log_budget: PluginExceptionLogBudget | None = None,
    ) -> TargetCollectionResult:
        started_at = time.monotonic()
        return await self._execute_target(
            request,
            target,
            lease,
            target_started_at=started_at,
            plugin_exception_log_budget=plugin_exception_log_budget,
        )

    async def _execute_target(
        self,
        request: CollectionRequest,
        target: str,
        lease: RunLease,
        *,
        target_started_at: float,
        plugin_exception_log_budget: PluginExceptionLogBudget | None,
    ) -> TargetCollectionResult:
        preflight = await self._run_preflight(request, target)
        if preflight.status == PreflightStatus.UNREACHABLE:
            self._metrics.increment("target_unreachable_total")
            error_code = preflight.error_code or "target_unreachable"
            return TargetCollectionResult(
                target=target,
                status="unreachable",
                attempts=0,
                error_code=error_code,
                failed_stage=preflight.failed_stage,
            )

        credentials = await self._load_eligible_credentials(request, target)
        if credentials is None:
            return TargetCollectionResult(
                target=target,
                status="failed",
                attempts=0,
                error_code="credential_state_unavailable",
                failed_stage=FailureStage.CREDENTIAL,
            )
        if not credentials:
            return await self._no_credential_result(request, target)

        context_params = dict(request.params)
        context_params["_log_plugin_call_chain"] = True
        if plugin_exception_log_budget is not None:
            context_params["_plugin_exception_log_budget"] = plugin_exception_log_budget
        if preflight.connect_host:
            context_params["_validated_connect_host"] = preflight.connect_host
        context = TargetCollectionContext(
            task_id=request.task_id,
            plugin_ref=request.plugin_ref,
            fence=lease.fence,
            params=context_params,
            owner_id=lease.owner_id,
            attempt_id=lease.attempt_id,
        )
        return await self._credential_attempt_runner.run(
            request,
            target,
            credentials,
            context,
            target_started_at=target_started_at,
        )

    async def _load_eligible_credentials(self, request: CollectionRequest, target: str):
        try:
            return await self._credential_policy.eligible_credentials(request, target)
        except Exception as exc:  # noqa: BLE001 - 凭据状态失败隔离为单目标
            if not is_credential_state_redis_error(exc):
                raise
            self._metrics.increment("credential_state_redis_error_total")
            return None

    async def _run_preflight(self, request: CollectionRequest, target: str) -> PreflightResult:
        preflight_started = time.monotonic()
        try:
            async with asyncio.timeout(self._plan.preflight_timeout_seconds):
                return await self._preflight.check(
                    target,
                    request,
                    timeout_seconds=self._plan.preflight_timeout_seconds,
                )
        except TimeoutError:
            self._metrics.observe(
                "timeout_overshoot_seconds",
                max(
                    0.0,
                    time.monotonic() - preflight_started - self._plan.preflight_timeout_seconds,
                ),
            )
            self._metrics.increment("preflight_timeout_total")
            return PreflightResult(
                status=PreflightStatus.UNREACHABLE,
                error_code="preflight_timeout",
                failed_stage=(FailureStage.IP_PRECHECK if request.ip_precheck_enabled else FailureStage.OUTBOUND_POLICY),
            )
        finally:
            duration = time.monotonic() - preflight_started
            self._metrics.increment(
                "preflight_duration_seconds_total",
                duration,
            )
            self._metrics.observe("preflight_duration_seconds", duration)
            self._metrics.increment("preflight_total")

    async def _no_credential_result(self, request: CollectionRequest, target: str) -> TargetCollectionResult:
        self._metrics.increment("credential_cooldown_total")
        next_retry_at = None
        try:
            next_retry_at = await self._credential_policy.next_retry_at(request, target)
        except Exception as exc:  # noqa: BLE001 - 读冷冻时间失败不影响结果
            if not is_credential_state_redis_error(exc):
                raise
            self._metrics.increment("credential_state_redis_error_total")
        has_matching_credential = bool(self._credential_policy.matching_credentials(request, target))
        error_code = "no_valid_credential" if has_matching_credential else "no_matching_credential"
        logger.debug(
            "event=target_no_credential task_id=%s target=%s error_code=%s " "next_retry_at=%s",
            safe_log_value(request.task_id),
            safe_log_value(target, max_length=255),
            safe_log_value(error_code),
            next_retry_at,
        )
        return TargetCollectionResult(
            target=target,
            status="failed",
            attempts=0,
            error_code=error_code,
            value={"next_retry_at": next_retry_at},
            failed_stage=FailureStage.CREDENTIAL,
        )


def request_instance_id(request: CollectionRequest) -> str:
    """返回用于运行日志关联的业务实例 ID。"""

    tags = request.params.get("tags")
    tagged_instance_id = tags.get("instance_id") if isinstance(tags, dict) else None
    return str(request.params.get("instance_id") or tagged_instance_id or "-")
