from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("alerts", "0034_event_node_id"),
    ]
    operations = [
        migrations.AddField(
            model_name="actionrule",
            name="auto_execute",
            field=models.BooleanField(default=True, verbose_name="是否自动执行"),
        ),
    ]
