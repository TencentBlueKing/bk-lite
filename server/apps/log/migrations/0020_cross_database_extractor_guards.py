from django.db import migrations, models
from django.db.models import Count


def ensure_extractor_keys_unique(apps, schema_editor):
    alias = schema_editor.connection.alias
    LogExtractor = apps.get_model("log", "LogExtractor")
    attached = LogExtractor.objects.using(alias).filter(collect_instance_id__isnull=False)
    duplicate_name = (
        attached.values("collect_instance_id", "name").annotate(total=Count("id")).filter(total__gt=1).order_by("collect_instance_id", "name").first()
    )
    duplicate_order = (
        attached.values("collect_instance_id", "sort_order")
        .annotate(total=Count("id"))
        .filter(total__gt=1)
        .order_by("collect_instance_id", "sort_order")
        .first()
    )
    if duplicate_name is not None or duplicate_order is not None:
        raise RuntimeError("日志提取规则存在重复名称或顺序，请先完成业务核对再迁移")


class Migration(migrations.Migration):
    dependencies = [("log", "0019_k8sinstalltoken")]

    operations = [
        migrations.RunPython(ensure_extractor_keys_unique, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="logextractor",
            constraint=models.UniqueConstraint(
                fields=("collect_instance", "name"),
                name="log_extractor_instance_name_portable_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="logextractor",
            constraint=models.UniqueConstraint(
                fields=("collect_instance", "sort_order"),
                name="log_extractor_instance_order_portable_uniq",
            ),
        ),
    ]
