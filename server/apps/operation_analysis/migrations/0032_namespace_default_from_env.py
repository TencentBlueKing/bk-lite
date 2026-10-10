from django.db import migrations, models

import apps.operation_analysis.constants.nats_namespace


class Migration(migrations.Migration):
    dependencies = [
        ("operation_analysis", "0031_canvas_draft_checkpoint"),
    ]

    operations = [
        migrations.AlterField(
            model_name="namespace",
            name="namespace",
            field=models.CharField(
                default=apps.operation_analysis.constants.nats_namespace.resolve_nats_namespace,
                help_text="NATS服务端的命名空间,用于消息主题前缀",
                max_length=64,
                verbose_name="NATS命名空间",
            ),
        ),
    ]
