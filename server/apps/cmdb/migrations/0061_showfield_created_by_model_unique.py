import json

from django.apps import apps as global_apps
from django.core.management.color import no_style
from django.db import migrations, models

BACKUP_TABLE = "cmdb_showfield_duplicate_backup"
CONSTRAINT_NAME = "uniq_showfield_created_by_model"
_BACKUP_MODEL = None


def _backup_model():
    """备份表只存在于这次迁移，不进入模型状态。"""
    global _BACKUP_MODEL
    if _BACKUP_MODEL is not None:
        return _BACKUP_MODEL

    class ShowFieldDuplicateBackup(models.Model):
        original_id = models.BigIntegerField()
        created_by = models.CharField(max_length=50)
        model_id = models.CharField(max_length=100)
        show_fields = models.JSONField()
        created_at = models.DateTimeField()
        updated_at = models.DateTimeField()

        class Meta:
            app_label = "cmdb"
            db_table = BACKUP_TABLE

    model_name = ShowFieldDuplicateBackup._meta.model_name
    global_apps.all_models["cmdb"].pop(model_name, None)
    global_apps.clear_cache()
    _BACKUP_MODEL = ShowFieldDuplicateBackup
    return _BACKUP_MODEL


def _using(schema_editor):
    return schema_editor.connection.alias


def create_backup_table(apps, schema_editor):
    schema_editor.create_model(_backup_model())


def drop_backup_table(apps, schema_editor):
    schema_editor.delete_model(_backup_model())


def merge_duplicate_show_fields(apps, schema_editor):
    """同一用户和模型保留 updated_at 最新的一行；时间相同则保留更大的 id。"""
    show_field = apps.get_model("cmdb", "ShowField")
    backup = _backup_model()
    duplicate_groups = list(
        show_field.objects.using(_using(schema_editor))
        .values("created_by", "model_id")
        .annotate(row_count=models.Count("id"))
        .filter(row_count__gt=1)
    )
    for group in duplicate_groups:
        rows = list(
            show_field.objects.using(_using(schema_editor))
            .filter(created_by=group["created_by"], model_id=group["model_id"])
            .order_by("-updated_at", "-id")
        )
        removed_ids = []
        for row in rows[1:]:
            backup.objects.using(_using(schema_editor)).create(
                original_id=row.id,
                created_by=row.created_by,
                model_id=row.model_id,
                show_fields=row.show_fields,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            removed_ids.append(row.id)
        if removed_ids:
            show_field.objects.using(_using(schema_editor)).filter(id__in=removed_ids).delete()


def _load_show_fields(value):
    if isinstance(value, str):
        return json.loads(value)
    return value


def restore_duplicate_show_fields(apps, schema_editor):
    show_field = apps.get_model("cmdb", "ShowField")
    backed_up_rows = list(
        _backup_model().objects.using(_using(schema_editor)).order_by("original_id")
    )
    for row in backed_up_rows:
        show_field.objects.using(_using(schema_editor)).create(
            id=row.original_id,
            created_by=row.created_by,
            model_id=row.model_id,
            show_fields=_load_show_fields(row.show_fields),
        )
        show_field.objects.using(_using(schema_editor)).filter(pk=row.original_id).update(
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
    for statement in schema_editor.connection.ops.sequence_reset_sql(no_style(), [show_field]):
        schema_editor.execute(statement)


class Migration(migrations.Migration):
    dependencies = [
        ("cmdb", "0060_subscription_attribute_lifecycle"),
    ]

    operations = [
        migrations.RunPython(create_backup_table, drop_backup_table),
        migrations.RunPython(merge_duplicate_show_fields, restore_duplicate_show_fields),
        migrations.AddConstraint(
            model_name="showfield",
            constraint=models.UniqueConstraint(
                fields=("created_by", "model_id"),
                name=CONSTRAINT_NAME,
            ),
        ),
    ]
