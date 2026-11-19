from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from apps.core.logger import workflow_logger as logger
from apps.core.utils.license_capacity import filter_permission_map
from apps.core.utils.user_group import normalize_user_group_ids
from apps.system_mgmt.models import User
from apps.system_mgmt.services.user_access import is_account_expired
from apps.workflow.models import TriggerInvocation, Workflow, WorkflowExecution, WorkflowTrigger, WorkflowVersion
from apps.workflow.permissions import user_can_access_workflow
from apps.workflow.services.conductor import ConductorClient, ExecutionStartUnknown
from apps.workflow.services.definitions import DefinitionValidationError, validate_workflow_inputs
from apps.workflow.services.nats_contracts import build_nats_trigger_subject
from apps.workflow.services.runtime import reconcile_unknown_execution, start_execution
from apps.workflow.services.schedules import build_schedule_event, compile_schedule_config, next_schedule_runs


class TriggerConflict(ValueError):
    pass


class ScheduleChanged(TriggerConflict):
    """The due tick no longer belongs to the version selected by the scheduler."""


def _scheduled_identity(version: WorkflowVersion, node_key: str) -> dict | None:
    node = next((node for node in version.canvas_metadata.get("trigger_nodes", []) if node.get("id") == node_key), {})
    team_id = node.get("config", {}).get("execution_team_id")
    if team_id is None:
        # Existing versions have no delegated identity until an operator republishes.
        return None
    return {"username": version.created_by, "domain": version.domain, "team_id": team_id, "include_children": False}


def _authorize_schedule(workflow: Workflow, identity: dict) -> None:
    from apps.system_mgmt.nats.auth import build_user_authorization_context

    account = {"username": identity["username"], "domain": identity["domain"]}
    user = User.objects.filter(**account, disabled=False).first()
    if user is None or is_account_expired(user) or not get_user_model().objects.filter(**account, is_active=True).exists():
        raise TriggerConflict("定时执行账号不可用")
    user.group_list = normalize_user_group_ids(user.group_list)
    auth = build_user_authorization_context(user)
    groups = set(normalize_user_group_ids(auth["group_list"]))
    if identity["team_id"] not in groups:
        raise TriggerConflict("定时执行组织不在当前用户的可用组织内")
    user.is_superuser = auth["is_superuser"]
    if not user.is_superuser and "workflow-Execute" not in filter_permission_map(auth["permission"]).get("workflow", ()):
        raise TriggerConflict("定时执行账号缺少流程执行权限")
    if not any(
        user_can_access_workflow(user, current_team=owner_team, workflow=workflow, require_operate=True)
        for owner_team in groups.intersection(workflow.team)
    ):
        raise TriggerConflict("缺少流程实例操作权限")


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


@transaction.atomic
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
    desired_names: dict[str, str] = {}
    used_names: set[str] = set()
    for node in nodes:
        node_key = str(node["id"])
        base_name = str(node.get("name") or node_key)[:120]
        name = base_name
        ordinal = 1
        while name in used_names:
            ordinal += 1
            name = f"{base_name[:112]}（{ordinal}）"
        used_names.add(name)
        desired_names[node_key] = name

    # Release occupied names before assigning them. Retained node keys keep their endpoint and invocation IDs.
    workflow.triggers.exclude(node_key__in=desired_names).delete()
    for trigger in workflow.triggers.filter(name__in=used_names).only("id", "name", "node_key"):
        if trigger.name != desired_names[trigger.node_key]:
            trigger.name = uuid4().hex
            trigger.save(update_fields=("name",))

    for node in nodes:
        node_key = str(node["id"])
        trigger_type = str(node["trigger_type"])
        config = dict(node.get("config") or {})
        validate_trigger_configuration(trigger_type, config)
        runtime_config = {"subject": build_nats_trigger_subject(workflow.pk, node_key)} if trigger_type == WorkflowTrigger.Type.NATS else config
        trigger, _ = WorkflowTrigger.objects.update_or_create(
            workflow=workflow,
            node_key=node_key,
            defaults={
                "name": desired_names[node_key],
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


def invoke_trigger(
    trigger: WorkflowTrigger,
    *,
    inputs: dict,
    idempotency_key: str,
    started_by: str,
    domain: str,
    caller_identity: dict | None = None,
    scheduled_at: datetime | None = None,
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

    execution_team_id = None
    with transaction.atomic():
        locked_workflow = Workflow.all_objects.select_for_update().get(pk=trigger.workflow_id)
        locked_trigger = WorkflowTrigger.objects.select_for_update().get(pk=trigger.pk)
        if not locked_workflow.enabled or locked_workflow.deleted_at is not None or locked_workflow.status != Workflow.Status.PUBLISHED:
            raise TriggerConflict("流程已删除或未发布，不能创建新执行")
        if not locked_trigger.enabled:
            raise TriggerConflict("触发器已停用")
        if scheduled_at is not None and (
            locked_trigger.trigger_type != WorkflowTrigger.Type.SCHEDULE
            or locked_trigger.next_run_at != scheduled_at
            or locked_workflow.current_version != trigger.workflow.current_version
        ):
            raise ScheduleChanged("定时配置已更新")
        version = WorkflowVersion.objects.get(workflow=locked_workflow, version=locked_workflow.current_version)
        if locked_trigger.trigger_type == WorkflowTrigger.Type.SCHEDULE and scheduled_at is None and normalized_key.startswith("cron:"):
            raise DefinitionValidationError("手动触发不能使用定时调度的幂等键前缀")
        if scheduled_at is not None:
            caller_identity = _scheduled_identity(version, locked_trigger.node_key)
            if caller_identity is not None:
                started_by, domain = caller_identity["username"], caller_identity["domain"]
                execution_team_id = caller_identity["team_id"]
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
                existing_execution = invocation.execution
                if (
                    existing_execution.started_by != started_by
                    or existing_execution.domain != domain
                    or (caller_identity and caller_identity["team_id"] != existing_execution.effective_execution_team_id)
                ):
                    raise TriggerConflict("幂等键已被其他执行身份使用")
                if existing_execution.status == WorkflowExecution.Status.UNKNOWN:
                    existing_execution = reconcile_unknown_execution(existing_execution, client=client or ConductorClient())
                return existing_execution, False
            raise TriggerConflict("相同幂等键正在处理")
        trigger_pk = locked_trigger.pk
        trigger_type = locked_trigger.trigger_type
        invocation_id = invocation.pk
        entry_input_schema = locked_trigger.input_schema or {}

    conductor = client or ConductorClient()
    try:
        if scheduled_at is not None and caller_identity is not None:
            _authorize_schedule(locked_workflow, caller_identity)
        execution = start_execution(
            locked_workflow,
            version_number=version.version,
            execution_team_id=execution_team_id,
            inputs=validated_inputs,
            started_by=started_by,
            domain=domain,
            caller_identity=caller_identity,
            client=conductor,
            trigger_type=trigger_type,
            trigger_id=str(trigger_pk),
            entry_input_schema=entry_input_schema,
        )
    except ExecutionStartUnknown as error:
        # Keep the idempotency row bound so retries reconcile instead of starting again.
        with transaction.atomic():
            invocation = TriggerInvocation.objects.select_for_update().get(pk=invocation_id)
            if invocation.execution_id and invocation.execution_id != error.execution.id:
                return invocation.execution, False
            invocation.execution = error.execution
            invocation.save(update_fields=("execution", "updated_at"))
            WorkflowTrigger.objects.filter(pk=trigger_pk).update(last_run_at=timezone.now(), updated_at=timezone.now())
        raise
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
                scheduled_at=scheduled_at,
            )
        except ScheduleChanged:
            summary["skipped"] += 1
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
            WorkflowTrigger.objects.filter(
                pk=trigger.pk, workflow__current_version=trigger.workflow.current_version, next_run_at=scheduled_at
            ).update(
                next_run_at=next_run,
                updated_at=timezone.now(),
            )
    return summary
