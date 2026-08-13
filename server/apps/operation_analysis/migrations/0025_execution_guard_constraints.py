from django.db import migrations, models


class Migration(migrations.Migration):
    # PostgreSQL 不允许在更新存量外键行的同一事务内立即 ALTER TABLE。
    # 约束单独成迁移，既避开 pending trigger events，也保留每份迁移的原子性。
    dependencies = [("operation_analysis", "0024_cross_database_execution_guards")]

    operations = [
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
