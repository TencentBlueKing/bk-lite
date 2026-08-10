from django.db import migrations, models


def backfill_status(apps, schema_editor):
    snapshot = apps.get_model("patch_mgmt", "HostComplianceSnapshot")
    snapshot.objects.filter(satisfied=True).update(status="satisfied")
    snapshot.objects.filter(satisfied=False).update(status="missing")


class Migration(migrations.Migration):
    dependencies = [("patch_mgmt", "0004_patchsource_builtin_identity")]

    operations = [
        migrations.AddField(
            model_name="hostcompliancesnapshot",
            name="status",
            field=models.CharField(
                choices=[
                    ("satisfied", "满足"),
                    ("missing", "缺失"),
                    ("unknown", "未知"),
                    ("not_applicable", "不适用"),
                ],
                default="missing",
                max_length=32,
                verbose_name="评估结果",
            ),
        ),
        migrations.RunPython(backfill_status, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="hostbaselinebinding",
            name="compliance_status",
            field=models.CharField(
                choices=[
                    ("compliant", "合规"),
                    ("non_compliant", "不合规"),
                    ("pending", "待评估"),
                    ("evaluating", "评估中"),
                    ("failed", "评估失败"),
                    ("unconfigured", "未配置"),
                    ("unknown", "评估未知"),
                    ("not_applicable", "不适用"),
                ],
                default="pending",
                max_length=32,
                verbose_name="合规状态",
            ),
        ),
        migrations.AddField(
            model_name="governancetaskhost",
            name="execution_token",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                max_length=32,
                verbose_name="执行栅栏令牌",
            ),
        ),
    ]
