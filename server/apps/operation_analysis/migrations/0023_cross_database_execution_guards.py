from django.db import migrations, models
from django.db.models import Count


def ensure_execution_keys_unique(apps, schema_editor):
    alias = schema_editor.connection.alias
    DashboardReportExecution = apps.get_model("operation_analysis", "DashboardReportExecution")
    executions = DashboardReportExecution.objects.using(alias)
    duplicate_request = (
        executions.filter(subscription_id__isnull=False)
        .exclude(request_id="")
        .values("subscription_id", "request_id", "trigger_type")
        .annotate(total=Count("id"))
        .filter(total__gt=1)
        .order_by("subscription_id", "request_id", "trigger_type")
        .first()
    )
    duplicate_schedule = (
        executions.filter(
            subscription_id__isnull=False,
            trigger_type="scheduled",
            scheduled_time_utc__isnull=False,
        )
        .values("subscription_id", "scheduled_time_utc", "trigger_type")
        .annotate(total=Count("id"))
        .filter(total__gt=1)
        .order_by("subscription_id", "scheduled_time_utc", "trigger_type")
        .first()
    )
    if duplicate_request is not None or duplicate_schedule is not None:
        raise RuntimeError("报告执行存在重复幂等键或计划时间，请先完成业务核对再迁移")


def populate_execution_guards(apps, schema_editor):
    alias = schema_editor.connection.alias
    DashboardReportExecution = apps.get_model("operation_analysis", "DashboardReportExecution")
    executions = DashboardReportExecution.objects.using(alias)
    executions.exclude(request_id="").update(request_guard=True)
    executions.filter(trigger_type="scheduled", scheduled_time_utc__isnull=False).update(scheduled_guard=True)


def clear_execution_guards(apps, schema_editor):
    alias = schema_editor.connection.alias
    DashboardReportExecution = apps.get_model("operation_analysis", "DashboardReportExecution")
    DashboardReportExecution.objects.using(alias).update(request_guard=None, scheduled_guard=None)


class Migration(migrations.Migration):
    dependencies = [("operation_analysis", "0022_cross_database_active_share_guard")]

    operations = [
        migrations.RunPython(ensure_execution_keys_unique, migrations.RunPython.noop),
        migrations.AddField(
            model_name="dashboardreportexecution",
            name="request_guard",
            field=models.BooleanField(default=None, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="dashboardreportexecution",
            name="scheduled_guard",
            field=models.BooleanField(default=None, editable=False, null=True),
        ),
        migrations.RunPython(populate_execution_guards, clear_execution_guards),
        migrations.AddConstraint(
            model_name="dashboardreportexecution",
            constraint=models.UniqueConstraint(
                fields=("subscription", "request_id", "trigger_type", "request_guard"),
                name="uniq_dashboard_report_execution_request_guard",
            ),
        ),
        migrations.AddConstraint(
            model_name="dashboardreportexecution",
            constraint=models.UniqueConstraint(
                fields=("subscription", "scheduled_time_utc", "trigger_type", "scheduled_guard"),
                name="uniq_dashboard_report_execution_scheduled_guard",
            ),
        ),
    ]
