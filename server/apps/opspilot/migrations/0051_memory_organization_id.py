# Generated migration for adding organization_id to Memory model

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("opspilot", "0050_memoryspace_memory"),
    ]

    operations = [
        migrations.AddField(
            model_name="memory",
            name="organization_id",
            field=models.IntegerField(blank=True, db_index=True, null=True, verbose_name="组织ID"),
        ),
        migrations.AlterField(
            model_name="memory",
            name="owner_domain",
            field=models.CharField(blank=True, db_index=True, default="", max_length=255, verbose_name="创建者域"),
        ),
        migrations.AlterField(
            model_name="memory",
            name="owner_username",
            field=models.CharField(db_index=True, max_length=150, verbose_name="创建者用户名/组织名"),
        ),
        migrations.AddIndex(
            model_name="memory",
            index=models.Index(fields=["organization_id"], name="memory_mgmt_organiz_a1b2c3_idx"),
        ),
    ]
