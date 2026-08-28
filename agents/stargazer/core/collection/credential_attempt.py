"""凭据级尝试：可选协议探测、凭据轮换与正式采集。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from core.collection.contracts import (
    AccessProbe,
    AccessProbeResult,
    AccessProbeStatus,
    CollectionPlugin,
    CollectOutcome,
    CollectOutcomeStatus,
    CredentialFailureResult,
    TargetCollectionContext,
    TargetCollectionResult,
    TargetExecutorSettings,
)
from core.collection.credential_operations import CredentialOperationRunner
from core.collection.credential_policy import CredentialPolicy
from core.collection.enums import FailureStage
from core.collection.execution_plan import ExecutionPlan
from core.collection.metrics import CollectionMetrics
from core.collection.runtime import CollectionRequest
from core.infra.redis_client import is_credential_state_redis_error
from core.logger import logger, safe_log_value


class _AttemptAction(StrEnum):
    COLLECT = "collect"
    CONTINUE = "continue"
    RETURN = "return"


class CredentialAttemptRunner:
    """执行单目标的有界凭据轮换；调用方只接收一个稳定目标结果。"""

    def __init__(
        self,
        *,
        access_probe: AccessProbe | None,
        plugin: CollectionPlugin,
        credential_policy: CredentialPolicy,
        settings: TargetExecutorSettings,
        plan: ExecutionPlan,
        metrics: CollectionMetrics,
    ) -> None:
        self._credential_policy = credential_policy
        self._settings = settings
        self._metrics = metrics
        self._operations = CredentialOperationRunner(
            access_probe=access_probe,
            plugin=plugin,
            plan=plan,
            metrics=metrics,
        )

    async def _safe_record_success(
        self,
        request: CollectionRequest,
        target: str,
        credential,
    ) -> None:
        try:
            await self._credential_policy.record_success(request, target, credential)
        except Exception as exc:  # noqa: BLE001 - 写亲和失败不阻断成功结果
            if not is_credential_state_redis_error(exc):
                raise
            self._metrics.increment("credential_state_redis_error_total")
            logger.warning(
                "event=credential_success_persist_failed task_id=%s target=%s " "failed_stage=credential_state error_type=%s",
                safe_log_value(request.task_id),
                safe_log_value(target, max_length=255),
                type(exc).__name__,
            )

    async def _safe_record_auth_failure(
        self,
        request: CollectionRequest,
        target: str,
        credential,
        *,
        error_code: str,
    ) -> None:
        try:
            await self._credential_policy.record_auth_failure(
                request,
                target,
                credential,
                error_code=error_code,
            )
        except Exception as exc:  # noqa: BLE001 - 写冷冻失败不阻断轮换
            if not is_credential_state_redis_error(exc):
                raise
            self._metrics.increment("credential_state_redis_error_total")
            logger.warning(
                "event=credential_failure_persist_failed task_id=%s target=%s " "failed_stage=credential_state error_type=%s",
                safe_log_value(request.task_id),
                safe_log_value(target, max_length=255),
                type(exc).__name__,
            )

    async def run(
        self,
        request: CollectionRequest,
        target: str,
        credentials,
        context: TargetCollectionContext,
        *,
        target_started_at: float,
    ) -> TargetCollectionResult:
        attempts = 0
        no_response_attempts = 0
        credential_failures = []
        for credential in credentials:
            attempts += 1
            self._metrics.increment("credential_attempt_total")
            credential_id = str(credential.get("credential_id") or "")

            access = await self._operations.run_access_probe(
                target,
                credential,
                context,
                attempts,
                enabled=request.ip_precheck_enabled,
                target_started_at=target_started_at,
            )
            if isinstance(access, TargetCollectionResult):
                return replace(access, credential_failures=tuple(credential_failures))

            probe_decision = await self._apply_access_probe(
                request,
                target,
                credential,
                access,
                attempts=attempts,
                no_response_attempts=no_response_attempts,
            )
            if probe_decision.credential_failure:
                credential_failures.append(probe_decision.credential_failure)
            if probe_decision.action is _AttemptAction.RETURN:
                return replace(
                    probe_decision.result,
                    credential_failures=tuple(credential_failures),
                )
            if probe_decision.action is _AttemptAction.CONTINUE:
                no_response_attempts = probe_decision.no_response_attempts
                continue
            no_response_attempts = probe_decision.no_response_attempts

            outcome = await self._operations.run_collect(
                target,
                credential,
                context,
                target_started_at=target_started_at,
            )
            collect_decision = await self._apply_collect_outcome(
                request,
                target,
                credential,
                outcome,
                attempts=attempts,
                credential_id=credential_id,
            )
            if collect_decision.credential_failure:
                credential_failures.append(collect_decision.credential_failure)
            if collect_decision.action is _AttemptAction.RETURN:
                return replace(
                    collect_decision.result,
                    credential_failures=tuple(credential_failures),
                )
            # continue → 下一凭据

        return TargetCollectionResult(
            target=target,
            status="failed",
            attempts=attempts,
            error_code=("protocol_no_response" if attempts > 0 and no_response_attempts == attempts else "credentials_exhausted"),
            credential_failures=tuple(credential_failures),
            failed_stage=(FailureStage.ACCESS_PROBE if attempts > 0 and no_response_attempts == attempts else FailureStage.CREDENTIAL),
        )

    async def _apply_access_probe(
        self,
        request: CollectionRequest,
        target: str,
        credential,
        access: AccessProbeResult,
        *,
        attempts: int,
        no_response_attempts: int,
    ):
        credential_id = str(credential.get("credential_id") or "")
        if access.status == AccessProbeStatus.NOT_SUPPORTED:
            return _AttemptDecision(action=_AttemptAction.COLLECT, no_response_attempts=no_response_attempts)
        if access.status in {
            AccessProbeStatus.AUTH_FAILED,
            AccessProbeStatus.CAPABILITY_DENIED,
        }:
            error_code = access.error_code or access.status.value
            await self._safe_record_auth_failure(
                request,
                target,
                credential,
                error_code=error_code,
            )
            logger.debug(
                "event=access_probe_failed task_id=%s plugin_ref=%s "
                "model_id=%s target=%s "
                "credential_id=%s probe_status=%s error_code=%s action=rotate",
                safe_log_value(request.task_id),
                safe_log_value(request.plugin_ref),
                safe_log_value(request.params.get("model_id") or "-"),
                safe_log_value(target, max_length=255),
                safe_log_value(credential_id or "-"),
                access.status.value,
                safe_log_value(error_code),
            )
            return _AttemptDecision(
                action=_AttemptAction.CONTINUE,
                no_response_attempts=no_response_attempts,
                credential_failure=CredentialFailureResult(
                    credential_id=credential_id,
                    error_code=error_code,
                ),
            )
        if access.status == AccessProbeStatus.NO_RESPONSE:
            no_response_attempts += 1
            logger.debug(
                "event=access_probe_failed task_id=%s plugin_ref=%s "
                "model_id=%s target=%s "
                "credential_id=%s probe_status=%s error_code=%s "
                "no_response_attempts=%s",
                safe_log_value(request.task_id),
                safe_log_value(request.plugin_ref),
                safe_log_value(request.params.get("model_id") or "-"),
                safe_log_value(target, max_length=255),
                safe_log_value(credential_id or "-"),
                access.status.value,
                safe_log_value(access.error_code or access.status.value),
                no_response_attempts,
            )
            limit = self._settings.max_no_response_attempts
            if limit and no_response_attempts >= limit:
                return _AttemptDecision(
                    action=_AttemptAction.RETURN,
                    result=TargetCollectionResult(
                        target=target,
                        status="failed",
                        attempts=attempts,
                        credential_id=credential_id,
                        error_code="no_response_attempt_limit",
                        failed_stage=FailureStage.ACCESS_PROBE,
                    ),
                    no_response_attempts=no_response_attempts,
                )
            return _AttemptDecision(action=_AttemptAction.CONTINUE, no_response_attempts=no_response_attempts)
        if access.status == AccessProbeStatus.TARGET_UNREACHABLE:
            logger.debug(
                "event=target_unreachable task_id=%s plugin_ref=%s " "model_id=%s target=%s " "credential_id=%s reason=%s",
                safe_log_value(request.task_id),
                safe_log_value(request.plugin_ref),
                safe_log_value(request.params.get("model_id") or "-"),
                safe_log_value(target, max_length=255),
                safe_log_value(credential_id or "-"),
                safe_log_value(access.error_code or "target_unreachable"),
            )
            return _AttemptDecision(
                action=_AttemptAction.RETURN,
                result=TargetCollectionResult(
                    target=target,
                    status="unreachable",
                    attempts=attempts,
                    credential_id=credential_id,
                    error_code=access.error_code or "target_unreachable",
                    failed_stage=FailureStage.ACCESS_PROBE,
                ),
                no_response_attempts=no_response_attempts,
            )
        if access.status == AccessProbeStatus.RATE_LIMITED:
            logger.debug(
                "event=access_probe_failed task_id=%s plugin_ref=%s "
                "model_id=%s target=%s "
                "credential_id=%s probe_status=%s error_code=%s action=defer",
                safe_log_value(request.task_id),
                safe_log_value(request.plugin_ref),
                safe_log_value(request.params.get("model_id") or "-"),
                safe_log_value(target, max_length=255),
                safe_log_value(credential_id or "-"),
                access.status.value,
                safe_log_value(access.error_code or "rate_limited"),
            )
            return _AttemptDecision(
                action=_AttemptAction.RETURN,
                result=TargetCollectionResult(
                    target=target,
                    status="deferred",
                    attempts=attempts,
                    credential_id=credential_id,
                    error_code=access.error_code or "rate_limited",
                ),
                no_response_attempts=no_response_attempts,
            )
        if access.status in {
            AccessProbeStatus.SERVICE_UNAVAILABLE,
            AccessProbeStatus.TLS_VALIDATION_FAILED,
            AccessProbeStatus.PROTOCOL_MISMATCH,
            AccessProbeStatus.MISCONFIGURED,
        }:
            logger.debug(
                "event=access_probe_failed task_id=%s plugin_ref=%s "
                "model_id=%s target=%s "
                "credential_id=%s probe_status=%s error_code=%s action=stop",
                safe_log_value(request.task_id),
                safe_log_value(request.plugin_ref),
                safe_log_value(request.params.get("model_id") or "-"),
                safe_log_value(target, max_length=255),
                safe_log_value(credential_id or "-"),
                access.status.value,
                safe_log_value(access.error_code or access.status.value),
            )
            return _AttemptDecision(
                action=_AttemptAction.RETURN,
                result=TargetCollectionResult(
                    target=target,
                    status="failed",
                    attempts=attempts,
                    credential_id=credential_id,
                    error_code=access.error_code or access.status.value,
                    failed_stage=FailureStage.ACCESS_PROBE,
                ),
                no_response_attempts=no_response_attempts,
            )
        if access.status != AccessProbeStatus.READY:
            logger.debug(
                "event=access_probe_failed task_id=%s plugin_ref=%s "
                "model_id=%s target=%s "
                "credential_id=%s probe_status=%s error_code=access_probe_misconfigured",
                safe_log_value(request.task_id),
                safe_log_value(request.plugin_ref),
                safe_log_value(request.params.get("model_id") or "-"),
                safe_log_value(target, max_length=255),
                safe_log_value(credential_id or "-"),
                access.status.value,
            )
            return _AttemptDecision(
                action=_AttemptAction.RETURN,
                result=TargetCollectionResult(
                    target=target,
                    status="failed",
                    attempts=attempts,
                    credential_id=credential_id,
                    error_code="access_probe_misconfigured",
                    failed_stage=FailureStage.ACCESS_PROBE,
                ),
                no_response_attempts=no_response_attempts,
            )
        return _AttemptDecision(action=_AttemptAction.COLLECT, no_response_attempts=no_response_attempts)

    async def _apply_collect_outcome(
        self,
        request: CollectionRequest,
        target: str,
        credential,
        outcome: CollectOutcome,
        *,
        attempts: int,
        credential_id: str,
    ):
        if outcome.status == CollectOutcomeStatus.SUCCESS:
            await self._safe_record_success(request, target, credential)
            return _AttemptDecision(
                action=_AttemptAction.RETURN,
                result=TargetCollectionResult(
                    target=target,
                    status="success",
                    attempts=attempts,
                    credential_id=credential_id,
                    value=outcome.value,
                ),
            )
        if outcome.status == CollectOutcomeStatus.DEFERRED:
            return _AttemptDecision(
                action=_AttemptAction.RETURN,
                result=TargetCollectionResult(
                    target=target,
                    status="deferred",
                    attempts=attempts,
                    credential_id=credential_id,
                    value=outcome.value,
                ),
            )
        if outcome.status == CollectOutcomeStatus.AUTH_FAILED:
            error_code = outcome.error_code or "authentication_failed"
            await self._safe_record_auth_failure(
                request,
                target,
                credential,
                error_code=error_code,
            )
            return _AttemptDecision(
                action=_AttemptAction.CONTINUE,
                credential_failure=CredentialFailureResult(
                    credential_id=credential_id,
                    error_code=error_code,
                ),
            )
        if outcome.status == CollectOutcomeStatus.RETRY_CREDENTIAL:
            return _AttemptDecision(action=_AttemptAction.CONTINUE)
        if outcome.status == CollectOutcomeStatus.UNREACHABLE:
            return _AttemptDecision(
                action=_AttemptAction.RETURN,
                result=TargetCollectionResult(
                    target=target,
                    status="unreachable",
                    attempts=attempts,
                    credential_id=credential_id,
                    error_code=outcome.error_code or "target_unreachable",
                    detail=outcome.detail,
                    failed_stage=FailureStage.COLLECTION,
                ),
            )
        return _AttemptDecision(
            action=_AttemptAction.RETURN,
            result=TargetCollectionResult(
                target=target,
                status="failed",
                attempts=attempts,
                credential_id=credential_id,
                error_code=outcome.error_code or "collection_failed",
                detail=outcome.detail,
                value=outcome.value,
                failed_stage=FailureStage.COLLECTION,
            ),
        )


@dataclass(frozen=True)
class _AttemptDecision:
    action: _AttemptAction
    result: TargetCollectionResult | None = None
    no_response_attempts: int = 0
    credential_failure: CredentialFailureResult | None = None
