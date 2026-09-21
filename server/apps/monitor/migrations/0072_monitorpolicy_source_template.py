import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("monitor", "0071_collectconfig_applied_fingerprints"),
    ]

    operations = [
        migrations.AddField(
            model_name="monitorpolicy",
            name="source_template",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="issued_policies",
                to="monitor.policytemplate",
                verbose_name="来源策略模板",
            ),
        ),
    ]
