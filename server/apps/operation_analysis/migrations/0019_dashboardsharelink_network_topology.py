from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("operation_analysis", "0018_dashboardsharelink_resource_type"),
    ]

    operations = [
        migrations.AlterField(
            model_name="dashboardsharelink",
            name="resource_type",
            field=models.CharField(
                choices=[
                    ("dashboard", "仪表盘"),
                    ("topology", "拓扑图"),
                    ("architecture", "架构图"),
                    ("screen", "大屏"),
                    ("report", "报表"),
                    ("networkTopology", "网络拓扑"),
                ],
                db_index=True,
                default="dashboard",
                max_length=32,
            ),
        ),
    ]
