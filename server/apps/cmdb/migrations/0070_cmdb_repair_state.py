from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("cmdb", "0069_cmdb_scale_cursor"),
    ]

    operations = [
        migrations.CreateModel(
            name="CmdbRepairState",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("stage", models.CharField(max_length=200, unique=True)),
                ("cursor", models.CharField(blank=True, default="", max_length=512)),
                ("completed", models.BooleanField(default=False)),
                ("fingerprint", models.CharField(blank=True, default="", max_length=4000)),
                ("outcome", models.CharField(blank=True, default="", max_length=32)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "CMDB 实例修复断点",
                "verbose_name_plural": "CMDB 实例修复断点",
            },
        ),
    ]
