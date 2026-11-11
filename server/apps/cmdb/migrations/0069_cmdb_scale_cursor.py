from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("cmdb", "0068_alter_changerecord_scenario"),
    ]

    operations = [
        migrations.CreateModel(
            name="CmdbScaleCursor",
            fields=[
                ("key", models.CharField(max_length=64, primary_key=True, serialize=False)),
                ("payload", models.JSONField(default=dict)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "cmdb_scale_cursor",
            },
        ),
        migrations.AddField(
            model_name="autorelationpending",
            name="cursor_id",
            field=models.BigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="autorelationpending",
            name="phase",
            field=models.CharField(default="delete", max_length=16),
        ),
    ]
