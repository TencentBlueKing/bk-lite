from django.db import migrations, models


def backfill_applied_pack_version(apps, schema_editor):
    CollectConfig = apps.get_model("monitor", "CollectConfig")
    for config in CollectConfig.objects.select_related("monitor_plugin").iterator(chunk_size=500):
        plugin = config.monitor_plugin
        if plugin is None:
            continue
        plugin_fp = (getattr(plugin, "pack_content_sha256", None) or "").strip()
        applied_fp = (config.applied_content_sha256 or "").strip()
        # 仅回填已与当前插件内容对齐的配置；过期配置无法从哈希还原旧版本号。
        if plugin_fp and applied_fp == plugin_fp:
            version = plugin.pack_version or ""
            if config.applied_pack_version != version:
                config.applied_pack_version = version
                config.save(update_fields=["applied_pack_version"])


class Migration(migrations.Migration):
    dependencies = [
        ("monitor", "0070_monitorpolicy_compare_enrichment"),
    ]

    operations = [
        migrations.AddField(
            model_name="collectconfig",
            name="applied_content_sha256",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                max_length=64,
                verbose_name="已应用插件内容指纹",
            ),
        ),
        migrations.AddField(
            model_name="collectconfig",
            name="applied_rendered_sha256",
            field=models.CharField(
                blank=True,
                default="",
                max_length=64,
                verbose_name="上次模板渲染内容哈希",
            ),
        ),
        migrations.AddField(
            model_name="collectconfig",
            name="applied_pack_version",
            field=models.CharField(
                blank=True,
                default="",
                max_length=100,
                verbose_name="已应用的探针包版本",
            ),
        ),
        migrations.AddField(
            model_name="collectconfig",
            name="content_hand_edited",
            field=models.BooleanField(default=False, verbose_name="采集配置已被手改"),
        ),
        migrations.RunPython(backfill_applied_pack_version, migrations.RunPython.noop),
    ]
