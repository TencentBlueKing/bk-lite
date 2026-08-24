from django.db import migrations, models


class Migration(migrations.Migration):
    """结构过渡：仅加可空 UUID 列与断点表，不做数据回填。"""

    dependencies = [
        ("cmdb", "0044_alter_nodemgmtsyncconfig_auto_sync_enabled_default"),
    ]

    operations = [
        migrations.CreateModel(
            name="CmdbUuidMigrationState",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("stage", models.CharField(max_length=100, unique=True)),
                ("cursor", models.CharField(blank=True, default="", max_length=128)),
                ("completed", models.BooleanField(default=False)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "CMDB UUID 迁移断点",
                "verbose_name_plural": "CMDB UUID 迁移断点",
            },
        ),
        migrations.AlterField(
            model_name="changerecord",
            name="inst_id",
            field=models.BigIntegerField(
                blank=True,
                db_index=True,
                null=True,
                verbose_name="历史实例图ID",
            ),
        ),
        migrations.AddField(
            model_name="changerecord",
            name="inst_uuid",
            field=models.UUIDField(
                blank=True,
                db_index=True,
                null=True,
                verbose_name="实例UUID",
            ),
        ),
        migrations.AddField(
            model_name="configfileversion",
            name="instance_uuid",
            field=models.UUIDField(
                blank=True,
                db_index=True,
                help_text="主机实例 UUID",
                null=True,
            ),
        ),
        migrations.AddIndex(
            model_name="configfileversion",
            index=models.Index(fields=["instance_uuid", "file_path"], name="cmdb_cfg_uuid_path_idx"),
        ),
    ]
