from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("operation_analysis", "0017_dashboard_share_link"),
    ]

    operations = [
        migrations.AddField(
            model_name="dashboardsharelink",
            name="resource_type",
            field=models.CharField(
                choices=[
                    ("dashboard", "仪表盘"),
                    ("topology", "拓扑图"),
                    ("architecture", "架构图"),
                    ("screen", "大屏"),
                    ("report", "报表"),
                ],
                db_index=True,
                default="dashboard",
                max_length=32,
            ),
        ),
        migrations.RemoveConstraint(
            model_name="dashboardsharelink",
            name="uniq_active_dashboard_share_by_sharer",
        ),
        migrations.AddConstraint(
            model_name="dashboardsharelink",
            constraint=models.UniqueConstraint(
                condition=models.Q(("status", "active")),
                fields=("resource_type", "dashboard_instance_id", "sharer_username", "sharer_domain"),
                name="uniq_active_canvas_share_by_sharer",
            ),
        ),
    ]
