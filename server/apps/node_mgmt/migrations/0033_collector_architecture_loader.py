from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("node_mgmt", "0032_architecture_support"),
    ]

    operations = [
        migrations.AddField(
            model_name="collector",
            name="cpu_architecture",
            field=models.CharField(blank=True, default="", max_length=20, verbose_name="CPU架构"),
        ),
        migrations.AlterUniqueTogether(
            name="collector",
            unique_together={("node_operating_system", "cpu_architecture", "name")},
        ),
    ]
