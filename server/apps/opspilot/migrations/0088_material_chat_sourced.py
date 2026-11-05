from django.db import migrations, models


def mark_server_assigned_chat_materials(apps, schema_editor):
    """给已经由对话写入、路径为 chat/{id}.txt 的资料补上标记。

    之后不再用路径分流。上传可以写成 chat/ 开头，但只有精确等于当时资料 ID 的
    服务端路径才是这条写入留下的，迁移只认这一种。
    """
    Material = apps.get_model("opspilot", "Material")
    matched = []
    for material in Material.objects.all().only("id", "source_relative_path").iterator():
        path = str(material.source_relative_path or "").replace("\\", "/").strip()
        if path == f"chat/{material.pk}.txt":
            matched.append(material.pk)
    if matched:
        Material.objects.filter(pk__in=matched).update(chat_sourced=True)


class Migration(migrations.Migration):
    dependencies = [
        ("opspilot", "0087_llmskill_allow_wiki_material_write"),
    ]

    operations = [
        migrations.AddField(
            model_name="material",
            name="chat_sourced",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(mark_server_assigned_chat_materials, migrations.RunPython.noop),
    ]
