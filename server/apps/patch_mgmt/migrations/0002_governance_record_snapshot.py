from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("patch_mgmt", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="governancetask",
            name="result_snapshot",
            field=models.JSONField(default=list, verbose_name="执行结果快照"),
        ),
        migrations.AddField(
            model_name="governancetask",
            name="source_record",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="derived_records",
                to="patch_mgmt.governancetask",
                verbose_name="来源执行记录",
            ),
        ),
        migrations.AddField(
            model_name="governancetask",
            name="source_risk_item_id",
            field=models.CharField(
                blank=True,
                default="",
                max_length=256,
                verbose_name="来源风险项ID",
            ),
        ),
    ]
