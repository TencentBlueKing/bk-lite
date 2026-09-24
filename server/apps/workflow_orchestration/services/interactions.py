from __future__ import annotations

import uuid
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.core.logger import workflow_orchestration_logger as logger
from apps.workflow_orchestration.models import WorkflowExecution, WorkflowInteraction
from apps.workflow_orchestration.services.conductor import ConductorClient, ConductorConflict


class InteractionConflict(ValueError):
    pass


class InteractionForbidden(PermissionError):
    pass


MAX_DELIVERY_ATTEMPTS = 10
_DELIVERY_ATTEMPTS_KEY = "_delivery_attempts"


def _delivery_attempts(payload: dict) -> int:
    raw = payload.get(_DELIVERY_ATTEMPTS_KEY, 0) if isinstance(payload, dict) else 0
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
        return 0
    return raw


def _clear_delivery_intent(interaction: WorkflowInteraction) -> None:
    interaction.delivery_token = None
    interaction.delivery_started_at = None
    interaction.delivery_payload = {}
    interaction.save(update_fields=("delivery_token", "delivery_started_at", "delivery_payload", "updated_at"))


def _bump_delivery_attempt(interaction: WorkflowInteraction) -> int:
    payload = dict(interaction.delivery_payload or {})
    attempts = _delivery_attempts(payload) + 1
    payload[_DELIVERY_ATTEMPTS_KEY] = attempts
    interaction.delivery_payload = payload
    interaction.delivery_started_at = timezone.now()
    interaction.save(update_fields=("delivery_payload", "delivery_started_at", "updated_at"))
    return attempts


def _abandon_delivery(interaction: WorkflowInteraction, *, reason: str, error_type: str) -> None:
    logger.error(
        "event=workflow_interaction_delivery_abandoned interaction_id=%s reason=%s error_type=%s",
        interaction.id,
        reason,
        error_type,
    )
    _clear_delivery_intent(interaction)


def _set_delivery_intent(interaction: WorkflowInteraction, payload: dict) -> uuid.UUID:
    if interaction.delivery_token:
        raise InteractionConflict("该人工处理项正在提交，请稍后刷新")
    token = uuid.uuid4()
    interaction.delivery_token = token
    interaction.delivery_started_at = timezone.now()
    interaction.delivery_payload = {**payload, _DELIVERY_ATTEMPTS_KEY: 0}
    interaction.save(update_fields=("delivery_token", "delivery_started_at", "delivery_payload", "updated_at"))
    return token


def _finalize_delivery(interaction_id, token: uuid.UUID) -> WorkflowInteraction:
    with transaction.atomic():
        interaction = WorkflowInteraction.objects.select_for_update().select_related("execution").get(pk=interaction_id)
        if interaction.delivery_token != token:
            raise InteractionConflict("人工处理项投递令牌已失效")
        if interaction.status != WorkflowInteraction.Status.PENDING:
            raise InteractionConflict("该人工处理项已被处理")
        payload = dict(interaction.delivery_payload or {})
        payload.pop(_DELIVERY_ATTEMPTS_KEY, None)
        handled_at = parse_datetime(str(payload.get("handled_at") or ""))
        interaction.status = payload["status"]
        interaction.operator = payload.get("operator") or ""
        interaction.operator_domain = payload.get("operator_domain") or ""
        interaction.decision = payload.get("decision") or ""
        interaction.comment = payload.get("comment") or ""
        interaction.output = payload["output"]
        interaction.handled_at = handled_at
        interaction.lock_version += 1
        interaction.delivery_token = None
        interaction.delivery_started_at = None
        interaction.delivery_payload = {}
        interaction.save(
            update_fields=(
                "status",
                "operator",
                "operator_domain",
                "decision",
                "comment",
                "output",
                "handled_at",
                "lock_version",
                "delivery_token",
                "delivery_started_at",
                "delivery_payload",
                "updated_at",
            )
        )
        execution = interaction.execution
        if not execution.interactions.filter(status=WorkflowInteraction.Status.PENDING).exclude(pk=interaction.pk).exists():
            execution.status = WorkflowExecution.Status.RUNNING
            execution.save(update_fields=("status", "updated_at"))
    return interaction


def _deliver_intent(interaction_id, token: uuid.UUID, conductor: ConductorClient) -> WorkflowInteraction:
    interaction = WorkflowInteraction.objects.select_related("execution").get(pk=interaction_id)
    if interaction.delivery_token != token:
        raise InteractionConflict("人工处理项投递令牌已失效")
    payload = interaction.delivery_payload
    conductor.complete_task(
        workflow_id=interaction.execution.conductor_workflow_id,
        task_id=interaction.conductor_task_id,
        output=payload["output"],
        worker_id=payload["worker_id"],
    )
    return _finalize_delivery(interaction_id, token)


def decide_interaction(
    interaction_id,
    *,
    username: str,
    domain: str,
    decision: str,
    comment: str,
    client: ConductorClient | None = None,
) -> WorkflowInteraction:
    normalized_decision = str(decision or "").upper()
    if normalized_decision not in {"APPROVED", "REJECTED"}:
        raise ValueError("decision 必须是 APPROVED 或 REJECTED")
    normalized_comment = str(comment or "").strip()
    if normalized_decision == "REJECTED" and not normalized_comment:
        raise ValueError("拒绝必须填写意见")

    conductor = client or ConductorClient()
    with transaction.atomic():
        interaction = WorkflowInteraction.objects.select_for_update().select_related("execution").get(pk=interaction_id)
        if interaction.status != WorkflowInteraction.Status.PENDING:
            raise InteractionConflict("该审批已被处理")
        if username not in interaction.candidate_users:
            raise InteractionForbidden("当前用户不是该审批的候选人")
        if interaction.interaction_type != WorkflowInteraction.Type.APPROVAL:
            raise InteractionConflict("该人工处理项不是审批")
        execution = interaction.execution
        if not execution.conductor_workflow_id:
            raise InteractionConflict("执行记录缺少 Conductor Workflow ID")

        handled_at = timezone.now()
        output = {
            "approved": normalized_decision == "APPROVED",
            "operator": username,
            "comment": normalized_comment,
            "handled_at": handled_at.isoformat(),
        }
        token = _set_delivery_intent(
            interaction,
            {
                "status": normalized_decision,
                "operator": username,
                "operator_domain": domain,
                "decision": normalized_decision,
                "comment": normalized_comment,
                "output": output,
                "handled_at": handled_at.isoformat(),
                "worker_id": f"bklite-human-{username}"[:100],
            },
        )
    return _deliver_intent(interaction_id, token, conductor)


def expire_due_interactions(*, client: ConductorClient | None = None, limit: int = 100) -> dict[str, int]:
    conductor = client or ConductorClient()
    due_ids = list(
        WorkflowInteraction.objects.filter(
            status=WorkflowInteraction.Status.PENDING,
            delivery_token__isnull=True,
            due_at__isnull=False,
            due_at__lte=timezone.now(),
        )
        .order_by("due_at", "id")
        .values_list("id", flat=True)[: max(1, min(int(limit), 100))]
    )
    summary = {"timed_out": 0, "failed": 0}
    for interaction_id in due_ids:
        try:
            with transaction.atomic():
                interaction = WorkflowInteraction.objects.select_for_update().select_related("execution").get(pk=interaction_id)
                if (
                    interaction.status != WorkflowInteraction.Status.PENDING
                    or interaction.delivery_token
                    or not interaction.due_at
                    or interaction.due_at > timezone.now()
                ):
                    continue
                execution = interaction.execution
                if not execution.conductor_workflow_id:
                    raise InteractionConflict("执行记录缺少 Conductor Workflow ID")
                timed_out_at = timezone.now()
                output = {
                    "approved": None,
                    "operator": None,
                    "comment": None,
                    "handled_at": None,
                    "timed_out_at": timed_out_at.isoformat(),
                }
                token = _set_delivery_intent(
                    interaction,
                    {
                        "status": WorkflowInteraction.Status.TIMED_OUT,
                        "operator": "",
                        "operator_domain": "",
                        "decision": "TIMED_OUT",
                        "comment": "",
                        "output": output,
                        "handled_at": timed_out_at.isoformat(),
                        "worker_id": "bklite-human-timeout",
                    },
                )
            _deliver_intent(interaction_id, token, conductor)
            summary["timed_out"] += 1
        except Exception as error:
            summary["failed"] += 1
            safe_error = RuntimeError("workflow interaction timeout failed")
            logger.error(
                "event=workflow_interaction_timeout_failed interaction_id=%s failed_stage=conductor_complete error_type=%s",
                interaction_id,
                type(error).__name__,
                exc_info=(type(safe_error), safe_error, error.__traceback__),
            )
    return summary


def retry_pending_interaction_deliveries(
    *,
    client: ConductorClient | None = None,
    limit: int = 100,
    retry_after_seconds: int = 30,
) -> dict[str, int]:
    conductor = client or ConductorClient()
    before = timezone.now() - timedelta(seconds=max(1, int(retry_after_seconds)))
    claims = list(
        WorkflowInteraction.objects.filter(
            status=WorkflowInteraction.Status.PENDING,
            delivery_token__isnull=False,
            delivery_started_at__lte=before,
        )
        .order_by("delivery_started_at", "id")
        .values_list("id", "delivery_token")[: max(1, min(int(limit), 100))]
    )
    summary = {"delivered": 0, "failed": 0, "abandoned": 0}
    for interaction_id, token in claims:
        try:
            _deliver_intent(interaction_id, token, conductor)
            summary["delivered"] += 1
        except InteractionConflict:
            continue
        except ConductorConflict as error:
            summary["abandoned"] += 1
            interaction = WorkflowInteraction.objects.filter(pk=interaction_id, delivery_token=token).first()
            if interaction is not None:
                _abandon_delivery(interaction, reason="conductor_conflict", error_type=type(error).__name__)
        except Exception as error:
            summary["failed"] += 1
            interaction = WorkflowInteraction.objects.filter(pk=interaction_id, delivery_token=token).first()
            if interaction is not None:
                attempts = _bump_delivery_attempt(interaction)
                if attempts >= MAX_DELIVERY_ATTEMPTS:
                    summary["abandoned"] += 1
                    _abandon_delivery(interaction, reason="max_attempts", error_type=type(error).__name__)
            safe_error = RuntimeError("workflow interaction delivery retry failed")
            logger.error(
                "event=workflow_interaction_delivery_retry_failed interaction_id=%s failed_stage=conductor_complete error_type=%s",
                interaction_id,
                type(error).__name__,
                exc_info=(type(safe_error), safe_error, error.__traceback__),
            )
    return summary
