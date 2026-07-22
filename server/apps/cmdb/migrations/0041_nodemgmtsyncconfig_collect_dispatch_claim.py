from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("cmdb", "0040_collectmodels_execution_claim_token"),
    ]

    operations = [
        migrations.AddField(
            model_name="nodemgmtsyncconfig",
            name="collect_dispatch_claim_token",
            field=models.CharField(blank=True, editable=False, max_length=64, null=True),
        ),
        migrations.AddField(
            model_name="nodemgmtsyncconfig",
            name="collect_dispatch_claim_version",
            field=models.PositiveBigIntegerField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="nodemgmtsyncconfig",
            name="collect_dispatch_claimed_at",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
    ]
