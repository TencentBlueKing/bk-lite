import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("alerts", "0031_alert_push_source_ids")]

    operations = [
        migrations.AddField(
            model_name="alertassignment",
            name="priority",
            field=models.PositiveSmallIntegerField(
                default=100,
                help_text="分派优先级，数值越大优先级越高",
                validators=[
                    django.core.validators.MinValueValidator(0),
                    django.core.validators.MaxValueValidator(100),
                ],
            ),
        ),
        migrations.AddConstraint(
            model_name="alertassignment",
            constraint=models.CheckConstraint(
                check=models.Q(("priority__gte", 0), ("priority__lte", 100)),
                name="alert_assign_priority_range",
            ),
        ),
        migrations.AddIndex(
            model_name="alertassignment",
            index=models.Index(
                fields=["is_active", "priority", "created_at", "id"],
                name="alert_assign_order_idx",
            ),
        ),
    ]
