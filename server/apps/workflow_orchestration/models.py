import uuid

from django.db import models

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo
from apps.workflow_orchestration.services.workflow_projections import workflow_trigger_types


class ActiveWorkflowManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)


class Workflow(TimeInfo, MaintainerInfo):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "草稿"
        PUBLISHED = "PUBLISHED", "已发布"

    name = models.CharField(max_length=120)
    description = models.CharField(max_length=500, blank=True, default="")
    team = models.JSONField(default=list)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    definition = models.JSONField(default=dict)
    canvas_metadata = models.JSONField(default=dict)
    trigger_types = models.JSONField(default=list)
    engine_name = models.CharField(max_length=100, unique=True, blank=True)
    current_version = models.PositiveIntegerField(default=0)
    enabled = models.BooleanField(default=False, db_index=True)
    has_draft = models.BooleanField(default=True, db_index=True)
    draft_revision = models.PositiveIntegerField(default=0)
    draft_base_version = models.PositiveIntegerField(default=0)
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)
    deleted_by = models.CharField(max_length=32, blank=True, default="")
    deleted_by_domain = models.CharField(max_length=100, blank=True, default="")

    objects = ActiveWorkflowManager()
    all_objects = models.Manager()

    class Meta:
        db_table = "workflow_orchestration_workflow"
        ordering = ("-updated_at", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=("name", "team"),
                condition=models.Q(deleted_at__isnull=True),
                name="uq_workflow_active_name_team",
            )
        ]

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        if self.current_version == 0:
            self.trigger_types = workflow_trigger_types(self.canvas_metadata)
            if update_fields is not None and "canvas_metadata" in update_fields:
                kwargs["update_fields"] = tuple({*update_fields, "trigger_types"})
        super().save(*args, **kwargs)
        if not self.engine_name:
            engine_name = f"bklite_workflow_{self.pk}"
            type(self).objects.filter(pk=self.pk).update(engine_name=engine_name)
            self.engine_name = engine_name


class WorkflowVersion(TimeInfo):
    workflow = models.ForeignKey(Workflow, on_delete=models.CASCADE, related_name="versions")
    version = models.PositiveIntegerField()
    definition = models.JSONField(default=dict)
    canvas_metadata = models.JSONField(default=dict)
    resource_snapshot = models.JSONField(default=dict)
    change_summary = models.JSONField(default=dict)
    created_by = models.CharField(max_length=32, default="")
    domain = models.CharField(max_length=100, default="domain.com")

    class Meta:
        db_table = "workflow_orchestration_version"
        ordering = ("-version",)
        constraints = [models.UniqueConstraint(fields=("workflow", "version"), name="uq_workflow_orchestration_version")]


class WorkflowTrigger(TimeInfo, MaintainerInfo):
    class Type(models.TextChoices):
        FORM = "FORM", "表单"
        SCHEDULE = "SCHEDULE", "定时"
        WEBHOOK = "WEBHOOK", "API/Webhook"
        NATS = "NATS", "NATS"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workflow = models.ForeignKey(Workflow, on_delete=models.CASCADE, related_name="triggers")
    node_key = models.CharField(max_length=100, blank=True, default="")
    name = models.CharField(max_length=120)
    trigger_type = models.CharField(max_length=16, choices=Type.choices)
    enabled = models.BooleanField(default=False, db_index=True)
    team = models.JSONField(default=list)
    input_schema = models.JSONField(default=dict)
    default_inputs = models.JSONField(default=dict)
    config = models.JSONField(default=dict)
    idempotency_window_seconds = models.PositiveIntegerField(default=3600)
    next_run_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_run_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "workflow_orchestration_trigger"
        ordering = ("-updated_at",)
        constraints = [
            models.UniqueConstraint(fields=("workflow", "name"), name="uq_workflow_trigger_name"),
            models.UniqueConstraint(fields=("workflow", "node_key"), name="uq_workflow_trigger_node_key"),
        ]

    def save(self, *args, **kwargs):
        if not self.node_key:
            self.node_key = f"legacy_{self.id}"
        super().save(*args, **kwargs)


class WorkflowExecution(TimeInfo):
    class Mode(models.TextChoices):
        PRODUCTION = "PRODUCTION", "正式"
        DEBUG = "DEBUG", "调试"

    class DebugKind(models.TextChoices):
        FULL = "FULL", "全流程"
        NODE = "NODE", "单节点"

    class Status(models.TextChoices):
        QUEUED = "QUEUED", "排队中"
        RUNNING = "RUNNING", "执行中"
        WAITING_APPROVAL = "WAITING_APPROVAL", "等待审批"
        TERMINATING = "TERMINATING", "终止中"
        SUCCEEDED = "SUCCEEDED", "成功"
        FAILED = "FAILED", "失败"
        TIMED_OUT = "TIMED_OUT", "已超时"
        TERMINATED = "TERMINATED", "已终止"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workflow = models.ForeignKey(Workflow, on_delete=models.PROTECT, related_name="executions")
    workflow_version = models.PositiveIntegerField()
    conductor_workflow_id = models.CharField(max_length=100, null=True, blank=True, unique=True)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.QUEUED, db_index=True)
    team = models.JSONField(default=list)
    input = models.JSONField(default=dict)
    output = models.JSONField(default=dict)
    has_warnings = models.BooleanField(default=False)
    warning_count = models.PositiveIntegerField(default=0)
    tasks = models.JSONField(default=list)
    definition_snapshot = models.JSONField(default=dict)
    resource_snapshot = models.JSONField(default=dict)
    target_snapshot = models.JSONField(default=dict)
    launch_token_hash = models.CharField(max_length=64, null=True, blank=True, unique=True)
    error_message = models.CharField(max_length=500, blank=True, default="")
    failed_stage = models.CharField(max_length=32, blank=True, default="")
    termination_reason = models.CharField(max_length=500, blank=True, default="")
    trigger_type = models.CharField(
        max_length=16,
        choices=WorkflowTrigger.Type.choices,
        default=WorkflowTrigger.Type.FORM,
        db_index=True,
    )
    trigger_id = models.CharField(max_length=100, blank=True, default="", db_index=True)
    mode = models.CharField(max_length=16, choices=Mode.choices, default=Mode.PRODUCTION, db_index=True)
    debug_kind = models.CharField(max_length=16, choices=DebugKind.choices, blank=True, default="")
    debug_task_reference = models.CharField(max_length=100, blank=True, default="")
    started_by = models.CharField(max_length=32, default="", db_index=True)
    domain = models.CharField(max_length=100, default="domain.com")
    finished_at = models.DateTimeField(null=True, blank=True)
    parent_execution = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reruns",
    )

    class Meta:
        db_table = "workflow_orchestration_execution"
        ordering = ("-created_at",)


class TriggerInvocation(TimeInfo):
    trigger = models.ForeignKey(WorkflowTrigger, on_delete=models.CASCADE, related_name="invocations")
    execution = models.ForeignKey(
        WorkflowExecution,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="trigger_invocations",
    )
    team = models.JSONField(default=list)
    idempotency_key = models.CharField(max_length=128)
    expires_at = models.DateTimeField(db_index=True)

    class Meta:
        db_table = "workflow_orchestration_trigger_invocation"
        constraints = [
            models.UniqueConstraint(
                fields=("trigger", "idempotency_key"),
                name="uq_workflow_trigger_idempotency",
            )
        ]


class WorkflowInteraction(TimeInfo):
    class Type(models.TextChoices):
        APPROVAL = "APPROVAL", "审批"

    class Status(models.TextChoices):
        PENDING = "PENDING", "待处理"
        APPROVED = "APPROVED", "已通过"
        REJECTED = "REJECTED", "已拒绝"
        TIMED_OUT = "TIMED_OUT", "已超时"
        CANCELLED = "CANCELLED", "已取消"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    execution = models.ForeignKey(WorkflowExecution, on_delete=models.CASCADE, related_name="interactions")
    interaction_type = models.CharField(max_length=24, choices=Type.choices)
    task_reference = models.CharField(max_length=100, db_index=True)
    conductor_task_id = models.CharField(max_length=100, db_index=True)
    title = models.CharField(max_length=120)
    description = models.CharField(max_length=500, blank=True, default="")
    candidate_users = models.JSONField(default=list)
    public_context = models.JSONField(default=dict)
    team = models.JSONField(default=list)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    operator = models.CharField(max_length=32, blank=True, default="")
    operator_domain = models.CharField(max_length=100, blank=True, default="")
    decision = models.CharField(max_length=16, blank=True, default="")
    comment = models.CharField(max_length=500, blank=True, default="")
    output = models.JSONField(default=dict)
    due_at = models.DateTimeField(null=True, blank=True, db_index=True)
    handled_at = models.DateTimeField(null=True, blank=True)
    lock_version = models.PositiveIntegerField(default=0)
    delivery_token = models.UUIDField(null=True, blank=True, editable=False, db_index=True)
    delivery_started_at = models.DateTimeField(null=True, blank=True)
    delivery_payload = models.JSONField(default=dict)

    class Meta:
        db_table = "workflow_orchestration_interaction"
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("execution", "conductor_task_id"),
                name="uq_workflow_interaction_conductor_task",
            )
        ]


class AtomDefinition(TimeInfo, MaintainerInfo):
    class SourceType(models.TextChoices):
        SYSTEM = "SYSTEM", "系统节点"
        PLATFORM = "PLATFORM", "平台能力"
        PACKAGE = "PACKAGE", "研发标准包"

    key = models.CharField(max_length=100, primary_key=True)
    name = models.CharField(max_length=120)
    category = models.CharField(max_length=80)
    description = models.CharField(max_length=500, blank=True, default="")
    driver = models.CharField(max_length=32, default="LOCAL")
    built_in = models.BooleanField(default=True)
    team = models.JSONField(default=list)
    input_schema = models.JSONField(default=dict)
    output_schema = models.JSONField(default=dict)
    ui_schema = models.JSONField(default=dict)
    execution_config = models.JSONField(default=dict)
    default_timeout_seconds = models.PositiveIntegerField(default=600)
    retry_count = models.PositiveSmallIntegerField(default=0)
    retry_delay_seconds = models.PositiveIntegerField(default=5)
    idempotent = models.BooleanField(default=False)
    idempotency_key = models.CharField(max_length=200, blank=True, default="")
    error_types = models.JSONField(default=list)
    safety_level = models.CharField(max_length=16, default="READ_ONLY")
    required_permissions = models.JSONField(default=list)
    resource_scope = models.CharField(max_length=32, default="ORGANIZATION")
    source_type = models.CharField(max_length=16, choices=SourceType.choices, default=SourceType.PLATFORM, db_index=True)

    class Meta:
        db_table = "workflow_orchestration_atom_definition"
        ordering = ("category", "name", "key")
        constraints = [models.UniqueConstraint(fields=("name",), name="uq_workflow_atom_name")]


class AtomConfigTemplate(TimeInfo, MaintainerInfo):
    organization_id = models.PositiveBigIntegerField(db_index=True)
    atom_key = models.CharField(max_length=100, db_index=True)
    name = models.CharField(max_length=120)
    parameters = models.JSONField(default=dict)

    class Meta:
        db_table = "workflow_orchestration_atom_config_template"
        ordering = ("-updated_at", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=("organization_id", "atom_key", "name"),
                name="uq_workflow_atom_config_template_name",
            )
        ]


class AtomExecution(TimeInfo):
    class Status(models.TextChoices):
        PENDING = "PENDING", "等待执行"
        RUNNING = "RUNNING", "执行中"
        COMPLETED = "COMPLETED", "成功"
        FAILED = "FAILED", "失败"
        SKIPPED = "SKIPPED", "已跳过"

    execution = models.ForeignKey(WorkflowExecution, on_delete=models.CASCADE, related_name="atom_executions")
    conductor_task_id = models.CharField(max_length=100, blank=True, default="", db_index=True)
    task_reference = models.CharField(max_length=100, db_index=True)
    atom_key = models.CharField(max_length=100)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    attempt = models.PositiveSmallIntegerField(default=1)
    job_task_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    input = models.JSONField(default=dict)
    output = models.JSONField(default=dict)
    error_type = models.CharField(max_length=100, blank=True, default="")
    error_message = models.CharField(max_length=500, blank=True, default="")
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    claim_token = models.UUIDField(null=True, blank=True, editable=False)
    lease_expires_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = "workflow_orchestration_atom_execution"
        ordering = ("created_at",)
        constraints = [models.UniqueConstraint(fields=("execution", "task_reference", "attempt"), name="uq_workflow_atom_execution_attempt")]


class ExecutionArtifact(TimeInfo, MaintainerInfo):
    class Kind(models.TextChoices):
        INSPECTION_REPORT = "INSPECTION_REPORT", "巡检报告"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    execution = models.ForeignKey(WorkflowExecution, on_delete=models.CASCADE, related_name="artifacts")
    atom_execution = models.ForeignKey(AtomExecution, on_delete=models.SET_NULL, null=True, blank=True, related_name="artifacts")
    team = models.JSONField(default=list)
    kind = models.CharField(max_length=32, choices=Kind.choices, default=Kind.INSPECTION_REPORT)
    format = models.CharField(max_length=8, choices=(("docx", "Word"), ("xlsx", "Excel")))
    object_key = models.CharField(max_length=500, unique=True)
    filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=120)
    sha256 = models.CharField(max_length=64)
    size = models.PositiveIntegerField()
    summary = models.JSONField(default=dict)
    expires_at = models.DateTimeField(db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "workflow_orchestration_execution_artifact"
        ordering = ("created_at",)
