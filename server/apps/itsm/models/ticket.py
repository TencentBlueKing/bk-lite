from django.db import models
from django.db.models import Exists, OuterRef, Q

from apps.itsm.models.base import ItsmModel
from apps.itsm.models.org import TicketStatus
from apps.itsm.models.workflow import Workflow, WorkflowVersion


class TicketQuerySet(models.QuerySet):
    def visible_to(self, username: str, see_all: bool = False, domain: str = "domain.com"):
        if see_all:
            return self
        if not username:
            return self.none()
        from apps.itsm.models.extend import TicketProxy

        principals = list(TicketProxy.objects.filter(agent=username, domain=domain, is_enabled=True).values_list("principal", flat=True))
        actors = [username, *principals]
        tasks = TicketTask.objects.filter(ticket_id=OuterRef("pk"), assignee__in=actors)
        followers = TicketFollower.objects.filter(ticket_id=OuterRef("pk"), username=username)
        return self.filter(Q(creator__in=actors) | Q(Exists(tasks)) | Q(Exists(followers)))


class TicketTag(ItsmModel):
    name = models.CharField(max_length=64)
    color = models.CharField(max_length=16, default="#1677ff")

    class Meta:
        db_table = "itsm_ticket_tag"
        unique_together = (("domain", "name"),)


class Ticket(ItsmModel):
    objects = TicketQuerySet.as_manager()
    sn = models.CharField(max_length=32, unique=True)
    title = models.CharField(max_length=200)
    service = models.ForeignKey("itsm.Service", null=True, blank=True, on_delete=models.SET_NULL, related_name="tickets")
    workflow = models.ForeignKey(Workflow, on_delete=models.PROTECT, related_name="tickets")
    workflow_version = models.ForeignKey(WorkflowVersion, null=True, blank=True, on_delete=models.PROTECT, related_name="tickets")
    status = models.ForeignKey(TicketStatus, null=True, blank=True, on_delete=models.PROTECT, related_name="tickets")
    creator = models.CharField(max_length=64)
    current_assignees = models.JSONField(default=list)
    form_data = models.JSONField(default=dict)
    creation_key = models.CharField(max_length=128, blank=True, null=True)
    creation_state = models.CharField(max_length=16, default="complete")
    process_instance_id = models.CharField(max_length=64, blank=True, default="")
    finished_at = models.DateTimeField(null=True, blank=True, db_index=True)
    is_test = models.BooleanField(default=False)
    tags = models.ManyToManyField(TicketTag, blank=True, related_name="tickets")

    class Meta:
        db_table = "itsm_ticket"
        constraints = [models.UniqueConstraint(fields=["domain", "creator", "creation_key"], name="itsm_unique_creation_key")]


class TicketTask(ItsmModel):
    class TaskStatus(models.TextChoices):
        PENDING = "pending", "待处理"
        CLAIMED = "claimed", "已认领"
        DONE = "done", "已完成"

    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="tasks")
    flowable_task_id = models.CharField(max_length=64, blank=True, default="")
    process_instance_id = models.CharField(max_length=64, blank=True, default="")
    node_id = models.CharField(max_length=64)
    node_name = models.CharField(max_length=128, blank=True, default="")
    assignee = models.CharField(max_length=64, blank=True, default="")
    status = models.CharField(max_length=16, choices=TaskStatus.choices, default=TaskStatus.PENDING)

    class Meta:
        db_table = "itsm_ticket_task"


class TicketComment(ItsmModel):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="comments")
    content = models.TextField()
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="replies")
    mentions = models.JSONField(default=list)

    class Meta:
        db_table = "itsm_ticket_comment"


class TicketAttachment(ItsmModel):
    comment = models.ForeignKey(TicketComment, null=True, blank=True, on_delete=models.SET_NULL, related_name="attachments")
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="attachments")
    task = models.ForeignKey(TicketTask, null=True, blank=True, on_delete=models.SET_NULL, related_name="attachments")
    field_key = models.CharField(max_length=64, blank=True, default="")
    object_name = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    size = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "itsm_ticket_attachment"


class TicketFollower(ItsmModel):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="followers")
    username = models.CharField(max_length=64)

    class Meta:
        db_table = "itsm_ticket_follower"
        unique_together = (("ticket", "username"),)


class TicketRelation(ItsmModel):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="relations")
    related = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="related_from")
    relation_type = models.CharField(max_length=32, default="related")

    class Meta:
        db_table = "itsm_ticket_relation"


class TicketSurvey(ItsmModel):
    ticket = models.OneToOneField(Ticket, on_delete=models.CASCADE, related_name="survey")
    score = models.PositiveSmallIntegerField()
    comment = models.CharField(max_length=500, blank=True, default="")
    answers = models.JSONField(default=list)

    class Meta:
        db_table = "itsm_ticket_survey"


class TicketLog(ItsmModel):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="logs")
    task = models.ForeignKey(TicketTask, null=True, blank=True, on_delete=models.SET_NULL, related_name="logs")
    action = models.CharField(max_length=32)
    operator = models.CharField(max_length=64)
    message = models.TextField(blank=True, default="")
    detail = models.JSONField(default=dict)

    class Meta:
        db_table = "itsm_ticket_log"


class TicketStartAttempt(models.Model):
    """工单首次启动或一次重新打开的引擎交接记录。"""

    ticket = models.ForeignKey(Ticket, related_name="start_attempts", on_delete=models.CASCADE)
    kind = models.CharField(max_length=12)
    previous_instance = models.CharField(max_length=64, default="", blank=True)
    business_key = models.CharField(max_length=100, unique=True)
    definition_id = models.CharField(max_length=255)
    operator = models.CharField(max_length=64)
    opinion = models.TextField(default="", blank=True)
    confirmations = models.JSONField(default=list, blank=True)
    state = models.CharField(max_length=12, default="ready")
    sent_at = models.DateTimeField(null=True)
    instance_id = models.CharField(max_length=64, default="", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "itsm_ticket_start_attempt"
        constraints = [models.UniqueConstraint(fields=("ticket", "kind", "previous_instance"), name="itsm_start_round_unique")]
        indexes = [models.Index(fields=("state", "id"), name="itsm_start_scan_idx")]


class ManualOperation(models.Model):
    """已授权的工单操作及其引擎回执。"""

    token = models.UUIDField(unique=True)
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="manual_operations")
    task = models.ForeignKey(TicketTask, on_delete=models.PROTECT, null=True)
    process_id = models.CharField(max_length=128)
    task_ref = models.CharField(max_length=128, blank=True)
    action = models.CharField(max_length=32)
    operator = models.CharField(max_length=64)
    status = models.CharField(max_length=16, default="prepared")
    payload = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "itsm_manual_operation"
        indexes = [models.Index(fields=["status", "updated_at"], name="itsm_manual_recovery_idx")]
