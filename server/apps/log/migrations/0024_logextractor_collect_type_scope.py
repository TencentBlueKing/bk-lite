from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("log", "0023_k8sinstalltoken_image_registry_prefix")]

    operations = [
        migrations.AddField(
            model_name="logextractor",
            name="collect_type",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.CASCADE,
                related_name="type_log_extractors",
                to="log.collecttype",
            ),
        ),
        migrations.AlterModelOptions(
            name="logextractor",
            options={"ordering": ("collect_instance_id", "collect_type_id", "sort_order", "id")},
        ),
        migrations.AddConstraint(
            model_name="logextractor",
            constraint=models.CheckConstraint(
                check=(
                    models.Q(collect_instance__isnull=False, collect_type__isnull=True)
                    | models.Q(collect_instance__isnull=True, collect_type__isnull=False)
                ),
                name="log_extractor_scope_xor",
            ),
        ),
        migrations.AddConstraint(
            model_name="logextractor",
            constraint=models.UniqueConstraint(
                condition=models.Q(collect_instance__isnull=True, collect_type__isnull=False),
                fields=("collect_type", "name"),
                name="log_extractor_type_name_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="logextractor",
            constraint=models.UniqueConstraint(
                condition=models.Q(collect_instance__isnull=True, collect_type__isnull=False),
                fields=("collect_type", "sort_order"),
                name="log_extractor_type_order_uniq",
            ),
        ),
        migrations.AddIndex(
            model_name="logextractor",
            index=models.Index(fields=("collect_type", "sort_order", "id"), name="log_extractor_type_order_idx"),
        ),
    ]
