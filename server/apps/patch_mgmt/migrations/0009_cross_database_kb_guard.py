from django.db import migrations, models
from django.db.models import Count


def ensure_kb_numbers_unique(apps, schema_editor):
    alias = schema_editor.connection.alias
    WindowsPatchDetail = apps.get_model("patch_mgmt", "WindowsPatchDetail")
    details = WindowsPatchDetail.objects.using(alias)
    duplicate = details.exclude(kb_number="").values("kb_number").annotate(total=Count("patch_id")).filter(total__gt=1).order_by("kb_number").first()
    if duplicate is not None:
        raise RuntimeError("Windows 补丁存在重复 KB 编号，请先完成业务核对再迁移")


def populate_kb_number_guard(apps, schema_editor):
    alias = schema_editor.connection.alias
    WindowsPatchDetail = apps.get_model("patch_mgmt", "WindowsPatchDetail")
    details = WindowsPatchDetail.objects.using(alias)
    details.exclude(kb_number="").update(kb_number_guard=True)


def clear_kb_number_guard(apps, schema_editor):
    alias = schema_editor.connection.alias
    apps.get_model("patch_mgmt", "WindowsPatchDetail").objects.using(alias).update(kb_number_guard=None)


class Migration(migrations.Migration):
    dependencies = [("patch_mgmt", "0008_patch_deleted_source_snapshots")]

    operations = [
        migrations.RunPython(ensure_kb_numbers_unique, migrations.RunPython.noop),
        migrations.AddField(
            model_name="windowspatchdetail",
            name="kb_number_guard",
            field=models.BooleanField(default=None, editable=False, null=True),
        ),
        migrations.RunPython(populate_kb_number_guard, clear_kb_number_guard),
        migrations.AddConstraint(
            model_name="windowspatchdetail",
            constraint=models.UniqueConstraint(
                fields=("kb_number", "kb_number_guard"),
                name="patch_windows_unique_nonempty_kb_guard",
            ),
        ),
    ]
