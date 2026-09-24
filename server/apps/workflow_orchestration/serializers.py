from rest_framework import serializers

from apps.core.utils.team_utils import get_current_team
from apps.workflow_orchestration.models import (
    AtomConfigTemplate,
    AtomDefinition,
    AtomExecution,
    ExecutionArtifact,
    Workflow,
    WorkflowExecution,
    WorkflowInteraction,
    WorkflowTrigger,
    WorkflowVersion,
)
from apps.workflow_orchestration.permissions import workflow_permissions
from apps.workflow_orchestration.services.config_templates import AtomConfigTemplateError, sanitize_atom_template_parameters
from apps.workflow_orchestration.services.data_contracts import normalize_workflow_data_contract
from apps.workflow_orchestration.services.definitions import DefinitionValidationError, validate_conductor_definition
from apps.workflow_orchestration.services.workflow_projections import workflow_trigger_types
from apps.workflow_orchestration.utils.i18n import serializer_message

WORKFLOW_NAME_CONFLICT_MESSAGE = "同一组织下已存在同名流程"


class SchedulePreviewRequestSerializer(serializers.Serializer):
    config = serializers.DictField()
    count = serializers.IntegerField(required=False, default=6, min_value=1, max_value=10)


class NatsTestSessionRequestSerializer(serializers.Serializer):
    workflow_id = serializers.IntegerField(min_value=1)
    node_key = serializers.RegexField(r"^[A-Za-z][A-Za-z0-9_-]{0,99}$")


class NatsTestListenRequestSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=2048, trim_whitespace=True)


class WebhookTestSessionRequestSerializer(serializers.Serializer):
    workflow_id = serializers.IntegerField(min_value=1)
    node_key = serializers.RegexField(r"^[A-Za-z][A-Za-z0-9_-]{0,99}$")


class WebhookTestListenRequestSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=2048, trim_whitespace=True)


def validate_workflow_name_available(name, *, team, exclude_id=None):
    queryset = Workflow.all_objects.filter(
        name__iexact=name,
        team=team,
        deleted_at__isnull=True,
    )
    if exclude_id is not None:
        queryset = queryset.exclude(pk=exclude_id)
    if queryset.exists():
        raise serializers.ValidationError(WORKFLOW_NAME_CONFLICT_MESSAGE)
    return name


class WorkflowDuplicateRequestSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120, trim_whitespace=True)

    def validate_name(self, value):
        return validate_workflow_name_available(value, team=self.context["team"])


class WorkflowSerializer(serializers.ModelSerializer):
    permission = serializers.SerializerMethodField()
    trigger_summary = serializers.SerializerMethodField()
    recent_execution_status = serializers.CharField(read_only=True, allow_null=True)
    recent_execution_at = serializers.DateTimeField(read_only=True, allow_null=True)

    @staticmethod
    def get_trigger_summary(workflow):
        published = {item.trigger_type for item in getattr(workflow, "trigger_definitions", [])}
        if published:
            return sorted(published)
        return workflow.trigger_types or workflow_trigger_types(workflow.canvas_metadata)

    def get_permission(self, workflow):
        return workflow_permissions(self.context.get("request"), workflow)

    def validate_name(self, value):
        if self.instance is not None:
            team = self.instance.team
            exclude_id = self.instance.pk
        else:
            request = self.context.get("request")
            try:
                team = [int(get_current_team(request))]
            except (TypeError, ValueError) as error:
                raise serializers.ValidationError("缺少或非法的 current_team") from error
            exclude_id = None
        return validate_workflow_name_available(value, team=team, exclude_id=exclude_id)

    class Meta:
        model = Workflow
        fields = (
            "id",
            "name",
            "description",
            "team",
            "status",
            "definition",
            "canvas_metadata",
            "engine_name",
            "current_version",
            "enabled",
            "has_draft",
            "draft_revision",
            "draft_base_version",
            "trigger_summary",
            "recent_execution_status",
            "recent_execution_at",
            "permission",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "team",
            "status",
            "engine_name",
            "current_version",
            "enabled",
            "has_draft",
            "draft_revision",
            "draft_base_version",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
        )

    def validate_definition(self, value):
        try:
            atom_catalog = None
            request = self.context.get("request")
            if request is not None:
                from apps.workflow_orchestration.services.atom_registry import available_atom_catalog

                atom_catalog = available_atom_catalog(int(get_current_team(request)))
            return validate_conductor_definition(
                value,
                atom_catalog=atom_catalog,
                strict_inputs=False,
                allow_empty_tasks=True,
            )
        except DefinitionValidationError as error:
            raise serializers.ValidationError(str(error)) from error
        except (TypeError, ValueError) as error:
            raise serializers.ValidationError("缺少或非法的 current_team") from error

    def validate_canvas_metadata(self, value):
        try:
            metadata, _ = normalize_workflow_data_contract(value)
            return metadata
        except DefinitionValidationError as error:
            raise serializers.ValidationError(str(error)) from error


class WorkflowVersionSerializer(serializers.ModelSerializer):
    execution_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = WorkflowVersion
        fields = (
            "id",
            "version",
            "definition",
            "canvas_metadata",
            "resource_snapshot",
            "change_summary",
            "created_by",
            "domain",
            "execution_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class AtomDefinitionSerializer(serializers.ModelSerializer):
    node_type = serializers.SerializerMethodField()

    @staticmethod
    def get_node_type(atom):
        return "ACTION"

    class Meta:
        model = AtomDefinition
        fields = (
            "key",
            "name",
            "category",
            "node_type",
            "description",
            "source_type",
            "input_schema",
            "output_schema",
            "ui_schema",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class AtomDefinitionSummarySerializer(AtomDefinitionSerializer):
    """Card-list payload without schemas, which are loaded from detail."""

    class Meta(AtomDefinitionSerializer.Meta):
        fields = tuple(field for field in AtomDefinitionSerializer.Meta.fields if field not in {"input_schema", "output_schema", "ui_schema"})
        read_only_fields = fields


class AtomConfigTemplateSerializer(serializers.ModelSerializer):
    parameters = serializers.JSONField()

    class Meta:
        model = AtomConfigTemplate
        fields = (
            "id",
            "name",
            "atom_key",
            "parameters",
            "organization_id",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "organization_id",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
        )

    def validate_name(self, value):
        name = value.strip()
        if not name:
            raise serializers.ValidationError("模板名称不能为空")
        return name

    def validate(self, attrs):
        team = self.context["team"]
        atom_key = attrs.get("atom_key", getattr(self.instance, "atom_key", ""))
        if self.instance is not None and "atom_key" in attrs and atom_key != self.instance.atom_key:
            raise serializers.ValidationError({"atom_key": "不能修改配置模板所属原子"})
        if "parameters" in attrs:
            if not isinstance(attrs["parameters"], dict):
                raise serializers.ValidationError({"parameters": "配置模板参数必须是对象"})
            try:
                attrs["parameters"] = sanitize_atom_template_parameters(
                    team=team,
                    atom_key=atom_key,
                    parameters=attrs["parameters"],
                )
            except AtomConfigTemplateError as error:
                raise serializers.ValidationError({"parameters": str(error)}) from error
        name = attrs.get("name", getattr(self.instance, "name", ""))
        duplicate = AtomConfigTemplate.objects.filter(
            organization_id=team,
            atom_key=atom_key,
            name__iexact=name,
        )
        if self.instance is not None:
            duplicate = duplicate.exclude(pk=self.instance.pk)
        if duplicate.exists():
            raise serializers.ValidationError({"name": "当前原子下已存在同名配置模板"})
        return attrs


class AtomExecutionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AtomExecution
        fields = (
            "id",
            "conductor_task_id",
            "task_reference",
            "atom_key",
            "status",
            "attempt",
            "job_task_id",
            "input",
            "output",
            "error_type",
            "error_message",
            "started_at",
            "finished_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class ExecutionArtifactSerializer(serializers.ModelSerializer):
    download_url = serializers.SerializerMethodField()

    @staticmethod
    def get_download_url(artifact):
        # 前端通过统一 Axios 代理下载，以便携带当前用户凭据。
        return f"/workflow_orchestration/api/artifacts/{artifact.id}/download/"

    class Meta:
        model = ExecutionArtifact
        fields = (
            "id",
            "kind",
            "format",
            "filename",
            "content_type",
            "sha256",
            "size",
            "summary",
            "expires_at",
            "deleted_at",
            "download_url",
            "created_at",
        )
        read_only_fields = fields


class WorkflowExecutionSerializer(serializers.ModelSerializer):
    workflow_name = serializers.CharField(source="workflow.name", read_only=True)
    workflow_enabled = serializers.BooleanField(source="workflow.enabled", read_only=True)
    workflow_deleted = serializers.SerializerMethodField()
    duration_ms = serializers.SerializerMethodField()
    atom_executions = AtomExecutionSerializer(many=True, read_only=True)
    artifacts = ExecutionArtifactSerializer(many=True, read_only=True)
    parent_execution = serializers.SerializerMethodField()
    permission = serializers.SerializerMethodField()

    def get_permission(self, execution):
        return workflow_permissions(self.context.get("request"), execution.workflow)

    @staticmethod
    def get_parent_execution(execution):
        return str(execution.parent_execution_id) if execution.parent_execution_id else None

    @staticmethod
    def get_workflow_deleted(execution):
        return execution.workflow.deleted_at is not None

    @staticmethod
    def get_duration_ms(execution):
        if execution.finished_at is None:
            return None
        return max(0, int((execution.finished_at - execution.created_at).total_seconds() * 1000))

    class Meta:
        model = WorkflowExecution
        fields = (
            "id",
            "workflow",
            "workflow_name",
            "workflow_enabled",
            "workflow_deleted",
            "workflow_version",
            "conductor_workflow_id",
            "status",
            "has_warnings",
            "warning_count",
            "trigger_type",
            "trigger_id",
            "mode",
            "debug_kind",
            "debug_task_reference",
            "parent_execution",
            "input",
            "output",
            "tasks",
            "definition_snapshot",
            "resource_snapshot",
            "target_snapshot",
            "atom_executions",
            "artifacts",
            "error_message",
            "failed_stage",
            "termination_reason",
            "started_by",
            "created_at",
            "finished_at",
            "duration_ms",
            "permission",
            "updated_at",
        )
        read_only_fields = fields


class WorkflowExecutionListSerializer(serializers.ModelSerializer):
    workflow_name = serializers.CharField(source="workflow.name", read_only=True)
    workflow_enabled = serializers.BooleanField(source="workflow.enabled", read_only=True)
    workflow_deleted = serializers.SerializerMethodField()
    artifact_count = serializers.IntegerField(read_only=True, default=0)
    parent_execution = serializers.SerializerMethodField()
    pending_approval_count = serializers.IntegerField(read_only=True, default=0)
    actionable_approval_ids = serializers.SerializerMethodField()
    duration_ms = serializers.SerializerMethodField()
    waiting_node_summary = serializers.SerializerMethodField()
    permission = serializers.SerializerMethodField()

    def get_permission(self, execution):
        return workflow_permissions(self.context.get("request"), execution.workflow)

    @staticmethod
    def get_parent_execution(execution):
        return str(execution.parent_execution_id) if execution.parent_execution_id else None

    @staticmethod
    def get_workflow_deleted(execution):
        return execution.workflow.deleted_at is not None

    @staticmethod
    def get_actionable_approval_ids(execution):
        return [str(item.id) for item in getattr(execution, "actionable_approvals", [])]

    @staticmethod
    def get_duration_ms(execution):
        if execution.finished_at is None:
            return None
        return max(0, int((execution.finished_at - execution.created_at).total_seconds() * 1000))

    def get_waiting_node_summary(self, execution):
        interactions = getattr(execution, "pending_interactions", [])
        labels = [item.title or item.task_reference for item in interactions[:3]]
        if len(interactions) > 3:
            labels.append(
                serializer_message(
                    self,
                    "message.waiting_items",
                    "等 {count} 项",
                    count=len(interactions),
                )
            )
        return " / ".join(labels)

    class Meta:
        model = WorkflowExecution
        fields = (
            "id",
            "workflow",
            "workflow_name",
            "workflow_enabled",
            "workflow_deleted",
            "workflow_version",
            "conductor_workflow_id",
            "status",
            "has_warnings",
            "warning_count",
            "trigger_type",
            "trigger_id",
            "mode",
            "debug_kind",
            "debug_task_reference",
            "parent_execution",
            "started_by",
            "error_message",
            "failed_stage",
            "termination_reason",
            "artifact_count",
            "created_at",
            "finished_at",
            "updated_at",
            "pending_approval_count",
            "actionable_approval_ids",
            "waiting_node_summary",
            "duration_ms",
            "permission",
        )
        read_only_fields = fields


class WorkflowInteractionSerializer(serializers.ModelSerializer):
    workflow_name = serializers.CharField(source="execution.workflow.name", read_only=True)
    execution_started_by = serializers.CharField(source="execution.started_by", read_only=True)
    workflow_version = serializers.IntegerField(source="execution.workflow_version", read_only=True)

    class Meta:
        model = WorkflowInteraction
        fields = (
            "id",
            "execution",
            "workflow_name",
            "workflow_version",
            "execution_started_by",
            "interaction_type",
            "task_reference",
            "title",
            "description",
            "candidate_users",
            "public_context",
            "status",
            "operator",
            "decision",
            "comment",
            "output",
            "due_at",
            "handled_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class WorkflowDashboardApprovalSerializer(serializers.ModelSerializer):
    workflow_name = serializers.CharField(source="execution.workflow.name", read_only=True)
    execution_started_by = serializers.CharField(source="execution.started_by", read_only=True)
    workflow_version = serializers.IntegerField(source="execution.workflow_version", read_only=True)

    class Meta:
        model = WorkflowInteraction
        fields = (
            "id",
            "execution",
            "workflow_name",
            "workflow_version",
            "execution_started_by",
            "task_reference",
            "title",
            "due_at",
            "created_at",
        )
        read_only_fields = fields


class WorkflowTriggerSerializer(serializers.ModelSerializer):
    workflow_name = serializers.CharField(source="workflow.name", read_only=True)

    def validate(self, attrs):
        from apps.workflow_orchestration.services.triggers import validate_trigger_configuration

        trigger_type = attrs.get("trigger_type", getattr(self.instance, "trigger_type", None))
        config = attrs.get("config", getattr(self.instance, "config", {}))
        try:
            validate_trigger_configuration(trigger_type, config)
        except DefinitionValidationError as error:
            raise serializers.ValidationError({"config": str(error)}) from error
        window = attrs.get("idempotency_window_seconds", getattr(self.instance, "idempotency_window_seconds", 3600))
        if not 60 <= window <= 86400:
            raise serializers.ValidationError({"idempotency_window_seconds": "必须在 60 到 86400 秒之间"})
        workflow = attrs.get("workflow", getattr(self.instance, "workflow", None))
        if workflow is not None:
            version = workflow.versions.filter(version=workflow.current_version).first() if workflow.current_version else None
            metadata = version.canvas_metadata if version is not None else workflow.canvas_metadata
            canonical_schema = (metadata or {}).get("input_schema") or {}
            supplied_schema = attrs.get("input_schema")
            if supplied_schema and supplied_schema != canonical_schema:
                raise serializers.ValidationError({"input_schema": "触发器必须使用已发布流程的统一输入 Schema"})
            attrs["input_schema"] = canonical_schema
        return attrs

    class Meta:
        model = WorkflowTrigger
        fields = (
            "id",
            "workflow",
            "node_key",
            "workflow_name",
            "name",
            "trigger_type",
            "enabled",
            "input_schema",
            "default_inputs",
            "config",
            "idempotency_window_seconds",
            "next_run_at",
            "last_run_at",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("node_key", "next_run_at", "last_run_at", "created_by", "updated_by", "created_at", "updated_at")
