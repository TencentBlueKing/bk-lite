from django.db import models

from apps.itsm.models.base import ItsmModel
from apps.itsm.models.form import FormModel


class WorkflowType(ItsmModel):
    name = models.CharField(max_length=128)
    key = models.CharField(max_length=64)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "itsm_workflow_type"
        unique_together = (("domain", "key"),)


class Workflow(ItsmModel):
    name = models.CharField(max_length=128)
    key = models.CharField(max_length=64)
    workflow_type = models.ForeignKey(WorkflowType, null=True, blank=True, on_delete=models.SET_NULL, related_name="workflows")
    form = models.ForeignKey(FormModel, null=True, blank=True, on_delete=models.SET_NULL, related_name="workflows")
    description = models.CharField(max_length=500, blank=True, default="")
    current_version = models.ForeignKey(
        "itsm.WorkflowVersion",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    is_enabled = models.BooleanField(default=True)

    class Meta:
        db_table = "itsm_workflow"
        unique_together = (("domain", "key"),)


class WorkflowVersion(ItsmModel):
    workflow = models.ForeignKey(Workflow, on_delete=models.CASCADE, related_name="versions")
    version_no = models.PositiveIntegerField()
    design = models.JSONField(default=dict)
    bpmn_xml = models.TextField(blank=True, default="")
    flowable_deployment_id = models.CharField(max_length=64, blank=True, default="")
    process_definition_id = models.CharField(max_length=128, blank=True, default="")
    process_definition_key = models.CharField(max_length=128, blank=True, default="")
    is_published = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "itsm_workflow_version"
        unique_together = (("workflow", "version_no"),)


class WorkflowStage(ItsmModel):
    workflow = models.ForeignKey(Workflow, on_delete=models.CASCADE, related_name="stages")
    key = models.CharField(max_length=64)
    name = models.CharField(max_length=128)
    order = models.PositiveIntegerField(default=0)
    node_ids = models.JSONField(default=list)

    class Meta:
        db_table = "itsm_workflow_stage"
        unique_together = (("workflow", "key"),)


class WorkflowVariable(ItsmModel):
    class Source(models.TextChoices):
        FORM = "form", "表单"
        CUSTOM = "custom", "自定义"
        SYSTEM = "system", "系统"

    workflow = models.ForeignKey(Workflow, on_delete=models.CASCADE, related_name="variables")
    key = models.CharField(max_length=64)
    name = models.CharField(max_length=128)
    value_type = models.CharField(max_length=32, default="string")
    source = models.CharField(max_length=16, choices=Source.choices, default=Source.CUSTOM)
    default = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "itsm_workflow_variable"
        unique_together = (("workflow", "key"),)
