from django.db import migrations, models


def copy_mcp_tags_to_user_tags(apps, schema_editor):
    from apps.opspilot.services.asset_tags import system_tags_for_tool, system_tags_from_manifest

    SkillTools = apps.get_model("opspilot", "SkillTools")
    for row in SkillTools.objects.all().iterator():
        if row.is_build_in:
            system_tags = system_tags_for_tool(row.name)
            if row.system_tags != system_tags:
                row.system_tags = system_tags
                row.save(update_fields=["system_tags"])
            continue
        tags = row.tags if isinstance(row.tags, list) else []
        row.user_tags = tags
        row.system_tags = []
        row.save(update_fields=["user_tags", "system_tags"])

    SkillPackage = apps.get_model("opspilot", "SkillPackage")
    for row in SkillPackage.objects.filter(is_build_in=True).iterator():
        manifest = row.manifest if isinstance(row.manifest, dict) else {}
        system_tags = system_tags_from_manifest(manifest)
        if row.system_tags != system_tags:
            row.system_tags = system_tags
            row.save(update_fields=["system_tags"])


class Migration(migrations.Migration):
    dependencies = [
        ("opspilot", "0085_chatattachment"),
    ]

    operations = [
        migrations.AddField(
            model_name="skillpackage",
            name="system_tags",
            field=models.JSONField(blank=True, default=list, verbose_name="系统标签"),
        ),
        migrations.AddField(
            model_name="skillpackage",
            name="user_tags",
            field=models.JSONField(blank=True, default=list, verbose_name="用户标签"),
        ),
        migrations.AddField(
            model_name="skilltools",
            name="system_tags",
            field=models.JSONField(blank=True, default=list, verbose_name="系统标签"),
        ),
        migrations.AddField(
            model_name="skilltools",
            name="user_tags",
            field=models.JSONField(blank=True, default=list, verbose_name="用户标签"),
        ),
        migrations.RunPython(copy_mcp_tags_to_user_tags, migrations.RunPython.noop),
    ]
