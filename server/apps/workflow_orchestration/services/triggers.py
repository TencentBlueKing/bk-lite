from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.core.logger import workflow_orchestration_logger as logger
from apps.workflow_orchestration.models import TriggerInvocation, Workflow, WorkflowExecution, WorkflowTrigger, WorkflowVersion
from apps.workflow_orchestration.services.conductor import ConductorClient
from apps.workflow_orchestration.services.definitions import DefinitionValidationError, validate_workflow_inputs
from apps.workflow_orchestration.services.nats_contracts import build_nats_trigger_subject
from apps.workflow_orchestration.services.runtime import start_execution
from apps.workflow_orchestration.services.schedules import build_schedule_event, compile_schedule_config, next_schedule_runs


class TriggerConflict(ValueError):
    pass


def calculate_next_run(trigger: WorkflowTrigger, *, after=None):
    if trigger.trigger_type != WorkflowTrigger.Type.SCHEDULE:
        return None
    validate_trigger_configuration(trigger.trigger_type, trigger.config)
    return next_schedule_runs(trigger.config, count=1, after=after)[0]


def validate_trigger_configuration(trigger_type: str, config: dict) -> None:
    if not isinstance(config, dict):
        raise DefinitionValidationError("触发器 config 必须是 JSON 对象")
    if trigger_type == WorkflowTrigger.Type.SCHEDULE:
        compile_schedule_config(
            config,
            timezone_name=str(config.get("timezone") or timezone.get_current_timezone_name()),
        )
    elif trigger_type == WorkflowTrigger.Type.WEBHOOK:
        if set(config).difference({"response_mode"}) or config.get("response_mode", "IMMEDIATE") not in {"WAIT", "IMMEDIATE"}:
            raise DefinitionValidationError("Webhook 响应模式非法")
    elif trigger_type == WorkflowTrigger.Type.FORM:
        if config:
            raise DefinitionValidationError("该触发类型不需要 config")
    elif trigger_type == WorkflowTrigger.Type.NATS:
        if config:
            raise DefinitionValidationError("NATS 触发器不需要配置参数")
    else:
        raise DefinitionValidationError("触发类型非法")


def sync_published_triggers(
    workflow: Workflow,
    canvas_metadata: dict,
    *,
    username: str,
    domain: str,
) -> None:
    """将发布版本中的触发节点幂等投影为运行时触发定义。"""
    nodes = canvas_metadata.get("trigger_nodes") or []
    if not isinstance(nodes, list):
        raise DefinitionValidationError("trigger_nodes 必须是数组")
    desired_keys: set[str] = set()
    used_names: dict[str, int] = {}
    for node in nodes:
        node_key = str(node["id"])
        desired_keys.add(node_key)
        base_name = str(node.get("name") or node_key)[:120]
        used_names[base_name] = used_names.get(base_name, 0) + 1
        name = base_name if used_names[base_name] == 1 else f"{base_name[:112]}（{used_names[base_name]}）"
        trigger_type = str(node["trigger_type"])
        config = dict(node.get("config") or {})
        validate_trigger_configuration(trigger_type, config)
        runtime_config = {"subject": build_nats_trigger_subject(workflow.pk, node_key)} if trigger_type == WorkflowTrigger.Type.NATS else config
        trigger, _ = WorkflowTrigger.objects.update_or_create(
            workflow=workflow,
            node_key=node_key,
            defaults={
                "name": name,
                "trigger_type": trigger_type,
                "enabled": workflow.enabled,
                "team": workflow.team,
                "input_schema": node.get("input_schema") or {},
                "default_inputs": {},
                "config": runtime_config,
                "idempotency_window_seconds": 3600,
                "created_by": username,
                "updated_by": username,
                "domain": domain,
                "updated_by_domain": domain,
            },
        )
        next_run = calculate_next_run(trigger) if workflow.enabled and trigger_type == WorkflowTrigger.Type.SCHEDULE else None
        if trigger.next_run_at != next_run:
            trigger.next_run_at = next_run
            trigger.save(update_fields=("next_run_at", "updated_at"))
    workflow.triggers.exclude(node_key__in=desired_keys).delete()


def invoke_trigger(
    trigger: WorkflowTrigger,
    *,
    inputs: dict,
    idempotency_key: str,
    started_by: str,
    domain: str,
    client: ConductorClient | None = None,
) -> tuple[WorkflowExecution, bool]:
    if not trigger.enabled:
        raise TriggerConflict("触发器已停用")
    if not trigger.workflow.enabled or trigger.workflow.deleted_at is not None or trigger.workflow.status != Workflow.Status.PUBLISHED:
        raise TriggerConflict("只有未删除的已发布流程可以触发")
    normalized_key = str(idempotency_key or "").strip()
    if trigger.trigger_type in {WorkflowTrigger.Type.WEBHOOK, WorkflowTrigger.Type.NATS} and not normalized_key:
        raise DefinitionValidationError("该触发方式必须提供幂等键")
    if not normalized_key:
        normalized_key = f"{trigger.trigger_type.lower()}-{timezone.now().isoformat()}"
    if len(normalized_key) > 128:
        raise DefinitionValidationError("幂等键最长 128 字符")

    with transaction.atomic():
        locked_workflow = Workflow.all_objects.select_for_update().get(pk=trigger.workflow_id)
        locked_trigger = WorkflowTrigger.objects.select_for_update().get(pk=trigger.pk)
        if not locked_workflow.enabled or locked_workflow.deleted_at is not None or locked_workflow.status != Workflow.Status.PUBLISHED:
            raise TriggerConflict("流程已删除或未发布，不能创建新执行")
        if not locked_trigger.enabled:
            raise TriggerConflict("触发器已停用")
        version = WorkflowVersion.objects.get(workflow=locked_workflow, version=locked_workflow.current_version)
        merged_inputs = {**locked_trigger.default_inputs, **inputs}
        validated_inputs = validate_workflow_inputs(
            merged_inputs,
            locked_trigger.input_schema or version.canvas_metadata.get("input_schema") or {},
        )
        existing = (
            TriggerInvocation.objects.select_for_update()
            .filter(
                trigger=locked_trigger,
                idempotency_key=normalized_key,
            )
            .first()
        )
        now = timezone.now()
        if existing is not None and existing.expires_at <= now:
            existing.idempotency_key = f"expired-{existing.pk}-{normalized_key}"[:128]
            existing.save(update_fields=("idempotency_key", "updated_at"))
        invocation, created = TriggerInvocation.objects.get_or_create(
            trigger=locked_trigger,
            idempotency_key=normalized_key,
            defaults={
                "team": locked_trigger.team,
                "expires_at": now + timedelta(seconds=locked_trigger.idempotency_window_seconds),
            },
        )
        if not created:
            if invocation.execution_id:
                return invocation.execution, False
            raise TriggerConflict("相同幂等键正在处理")
        workflow_id = locked_workflow.pk
        trigger_pk = locked_trigger.pk
        trigger_type = locked_trigger.trigger_type
        invocation_id = invocation.pk

    try:
        execution = start_execution(
            Workflow.all_objects.get(pk=workflow_id),
            inputs=validated_inputs,
            started_by=started_by,
            domain=domain,
            client=client or ConductorClient(),
            trigger_type=trigger_type,
            trigger_id=str(trigger_pk),
        )
    except Exception:
        TriggerInvocation.objects.filter(pk=invocation_id, execution__isnull=True).delete()
        raise
    with transaction.atomic():
        invocation = TriggerInvocation.objects.select_for_update().get(pk=invocation_id)
        if invocation.execution_id and invocation.execution_id != execution.id:
            return invocation.execution, False
        invocation.execution = execution
        invocation.save(update_fields=("execution", "updated_at"))
        WorkflowTrigger.objects.filter(pk=trigger_pk).update(last_run_at=timezone.now(), updated_at=timezone.now())
    return execution, True


def run_due_cron_triggers(*, now=None, limit: int = 100) -> dict[str, int]:
    current = now or timezone.now()
    limit = max(1, min(int(limit), 100))
    queryset = (
        WorkflowTrigger.objects.select_related("workflow")
        .filter(
            enabled=True,
            trigger_type=WorkflowTrigger.Type.SCHEDULE,
            workflow__status=Workflow.Status.PUBLISHED,
            workflow__enabled=True,
            workflow__deleted_at__isnull=True,
            next_run_at__lte=current,
        )
        .order_by("next_run_at", "id")[:limit]
    )
    summary = {"succeeded": 0, "skipped": 0, "failed": 0}
    for trigger in queryset:
        scheduled_at = trigger.next_run_at
        if scheduled_at is None:
            continue
        idempotency_key = f"cron:{scheduled_at.isoformat()}"[:128]
        try:
            schedule_event = build_schedule_event(
                trigger.config,
                scheduled_at=scheduled_at,
            )
            declared_fields = (trigger.input_schema or {}).get("properties") or {}
            _, created = invoke_trigger(
                trigger,
                inputs={key: value for key, value in schedule_event.items() if key in declared_fields},
                idempotency_key=idempotency_key,
                started_by="workflow-scheduler",
                domain="domain.com",
            )
        except Exception as error:
            summary["failed"] += 1
            safe_error = RuntimeError("workflow cron trigger failed")
            logger.error(
                "event=workflow_cron_trigger_failed trigger_id=%s failed_stage=invoke error_type=%s",
                trigger.id,
                type(error).__name__,
                exc_info=(type(safe_error), safe_error, error.__traceback__),
            )
        else:
            summary["succeeded" if created else "skipped"] += 1
        finally:
            next_run = calculate_next_run(trigger, after=max(current, scheduled_at))
            WorkflowTrigger.objects.filter(pk=trigger.pk, next_run_at=scheduled_at).update(
                next_run_at=next_run,
                updated_at=timezone.now(),
            )
    return summary
