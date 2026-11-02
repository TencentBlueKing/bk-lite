from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("apm", "0028_apmpolicy_scope"),
    ]

    operations = [
        migrations.AddField(
            model_name="apmpolicy",
            name="target_kind",
            field=models.CharField(
                choices=[("entry", "入口"), ("dependency", "下游依赖")],
                default="entry",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="apmpolicy",
            name="dependencies",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="apmpolicytargetstate",
            name="dependency",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="apmalert",
            name="dependency",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
