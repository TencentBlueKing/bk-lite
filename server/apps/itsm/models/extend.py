from django.db import models

from apps.itsm.models.base import ItsmModel
from apps.itsm.models.sla import SLAPolicy
from apps.itsm.models.ticket import Ticket
from apps.itsm.models.workflow import Workflow


class TicketSavedView(ItsmModel):
    username = models.CharField(max_length=64)
    name = models.CharField(max_length=128)
    filters = models.JSONField(default=dict)
    columns = models.JSONField(default=list)

    class Meta:
        db_table = "itsm_ticket_saved_view"


class TicketExportTask(ItsmModel):
    username = models.CharField(max_length=64)
    status = models.CharField(max_length=16, default="done")
    filename = models.CharField(max_length=128, default="")
    content_base64 = models.TextField(default="")
    ticket_count = models.PositiveIntegerField(default=0)
    is_async = models.BooleanField(default=False)
    request_payload = models.JSONField(default=dict)
    result_manifest = models.JSONField(default=dict)
    error = models.CharField(max_length=300, default="", blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "itsm_ticket_export_task"
        indexes = [models.Index(fields=["domain", "username", "is_async", "id"], name="itsm_export_owner_idx")]


class TicketProxy(ItsmModel):
    principal = models.CharField(max_length=64)
    agent = models.CharField(max_length=64)
    is_enabled = models.BooleanField(default=True)

    class Meta:
        db_table = "itsm_ticket_proxy"


class DecisionTable(ItsmModel):
    workflow = models.ForeignKey(Workflow, null=True, blank=True, on_delete=models.CASCADE, related_name="decisions")
    name = models.CharField(max_length=128)
    rules = models.JSONField(default=list)

    class Meta:
        db_table = "itsm_decision_table"


class Trigger(ItsmModel):
    name = models.CharField(max_length=128)
    event = models.CharField(max_length=64)
    action = models.CharField(max_length=32, default="tag")
    config = models.JSONField(default=dict)
    is_enabled = models.BooleanField(default=True)

    class Meta:
        db_table = "itsm_trigger"


class TriggerLog(ItsmModel):
    class Status(models.TextChoices):
        LEGACY = "legacy", "历史记录"
        PENDING = "pending", "处理中"
        SUCCESS = "success", "成功"
        FAILED = "failed", "失败"

    trigger = models.ForeignKey(Trigger, on_delete=models.SET_NULL, related_name="logs", null=True, blank=True)
    ticket_id = models.IntegerField(null=True, blank=True)
    run_id = models.PositiveBigIntegerField(null=True, blank=True)
    trigger_name = models.CharField(max_length=128, default="", blank=True)
    event = models.CharField(max_length=64, default="", blank=True)
    action = models.CharField(max_length=32, default="", blank=True)
    position = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.LEGACY)
    message = models.CharField(max_length=200, default="")

    class Meta:
        db_table = "itsm_trigger_log"
        indexes = [models.Index(fields=("ticket_id", "domain", "id"), name="itsm_triglog_ticket_idx")]


class ScheduledTask(ItsmModel):
    name = models.CharField(max_length=128)
    cron = models.CharField(max_length=64, default="0 9 * * 1-5")
    action = models.TextField(default="noop")
    is_enabled = models.BooleanField(default=True)
    next_run_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = "itsm_scheduled_task"


class ScheduledRun(ItsmModel):
    schedule = models.ForeignKey(ScheduledTask, on_delete=models.SET_NULL, null=True, related_name="runs")
    schedule_name = models.CharField(max_length=128)
    due_at = models.DateTimeField()
    status = models.CharField(max_length=16, default="running")
    message = models.CharField(max_length=255, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    ticket = models.ForeignKey(Ticket, on_delete=models.SET_NULL, null=True)

    class Meta:
        db_table = "itsm_scheduled_run"
        constraints = [models.UniqueConstraint(fields=["schedule", "due_at"], name="itsm_schedule_unique_slot")]


class DataSource(ItsmModel):
    name = models.CharField(max_length=128)
    kind = models.CharField(max_length=16, default="http")
    config = models.JSONField(default=dict)

    class Meta:
        db_table = "itsm_data_source"


class Announcement(ItsmModel):
    title = models.CharField(max_length=200)
    content = models.TextField(default="")
    is_enabled = models.BooleanField(default=True)

    class Meta:
        db_table = "itsm_announcement"


class ChangeWindow(ItsmModel):
    name = models.CharField(max_length=128)
    start_at = models.DateTimeField(null=True, blank=True)
    end_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "itsm_change_window"


class KnowledgeArticle(ItsmModel):
    title = models.CharField(max_length=200)
    content = models.TextField(default="")
    status = models.CharField(max_length=16, default="draft")

    class Meta:
        db_table = "itsm_knowledge_article"


class DutyShift(ItsmModel):
    name = models.CharField(max_length=128)
    members = models.JSONField(default=list)
    day = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "itsm_duty_shift"


class SurveyTemplate(ItsmModel):
    name = models.CharField(max_length=128)
    questions = models.JSONField(default=list)

    class Meta:
        db_table = "itsm_survey_template"


class PrintTemplate(ItsmModel):
    name = models.CharField(max_length=128)
    body = models.TextField(default="{{ title }}")

    class Meta:
        db_table = "itsm_print_template"


class Handover(ItsmModel):
    opinion = models.CharField(max_length=2000, blank=True, default="")
    from_user = models.CharField(max_length=64)
    to_user = models.CharField(max_length=64)
    ticket_ids = models.JSONField(default=list)
    results = models.JSONField(default=list)

    class Meta:
        db_table = "itsm_handover"


class TodoSync(ItsmModel):
    name = models.CharField(max_length=128)
    url = models.CharField(max_length=300, default="")

    class Meta:
        db_table = "itsm_todo_sync"


class SpecialOperationRule(ItsmModel):
    action = models.CharField(max_length=32)
    users = models.JSONField(default=list)

    class Meta:
        db_table = "itsm_special_operation_rule"


class ReportCard(ItsmModel):
    username = models.CharField(max_length=64)
    kind = models.CharField(max_length=32, default="ticket")

    class Meta:
        db_table = "itsm_report_card"


class VipUser(ItsmModel):
    username = models.CharField(max_length=64)
    is_enabled = models.BooleanField(default=True)

    class Meta:
        db_table = "itsm_vip_user"
        unique_together = (("domain", "username"),)


class AiSetting(ItsmModel):
    name = models.CharField(max_length=128)
    kind = models.CharField(max_length=16, default="assistant")
    prompt = models.TextField(default="")

    class Meta:
        db_table = "itsm_ai_setting"


class ChatSession(ItsmModel):
    visitor = models.CharField(max_length=64)
    agent = models.CharField(max_length=64, default="")
    status = models.CharField(max_length=16, default="open")

    class Meta:
        db_table = "itsm_chat_session"


class ChatMessage(ItsmModel):
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name="messages")
    sender = models.CharField(max_length=64)
    content = models.TextField()

    class Meta:
        db_table = "itsm_chat_message"


class BizObject(ItsmModel):
    name = models.CharField(max_length=128)
    key = models.CharField(max_length=64)
    status = models.CharField(max_length=16, default="draft")
    schema = models.JSONField(default=dict)

    class Meta:
        db_table = "itsm_biz_object"
        unique_together = (("domain", "key"),)


class BizRecord(ItsmModel):
    obj = models.ForeignKey(BizObject, on_delete=models.CASCADE, related_name="records")
    data = models.JSONField(default=dict)

    class Meta:
        db_table = "itsm_biz_record"


class EmailRule(ItsmModel):
    name = models.CharField(max_length=128)
    mailbox = models.CharField(max_length=200, default="")
    service_id = models.IntegerField(null=True, blank=True)
    is_enabled = models.BooleanField(default=False)

    class Meta:
        db_table = "itsm_email_rule"


class SearchField(ItsmModel):
    key = models.CharField(max_length=64)
    label = models.CharField(max_length=128)

    class Meta:
        db_table = "itsm_search_field"
        unique_together = (("domain", "key"),)


class UserPreference(ItsmModel):
    ticket_columns = models.JSONField(default=list)
    username = models.CharField(max_length=64)
    notify_events = models.JSONField(default=list)

    class Meta:
        db_table = "itsm_user_preference"
        unique_together = (("domain", "username"),)


class SLAPolicyLog(ItsmModel):
    policy = models.ForeignKey(SLAPolicy, on_delete=models.CASCADE, related_name="logs")
    message = models.CharField(max_length=200)

    class Meta:
        db_table = "itsm_sla_policy_log"


class AutoExecution(ItsmModel):
    ticket = models.ForeignKey(Ticket, null=True, blank=True, on_delete=models.CASCADE, related_name="auto_executions")
    kind = models.CharField(max_length=32)
    status = models.CharField(max_length=16, default="pending")
    detail = models.JSONField(default=dict)

    class Meta:
        db_table = "itsm_auto_execution"
