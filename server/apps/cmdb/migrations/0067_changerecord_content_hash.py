from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("cmdb", "0066_merge_reconcile_scan_and_auto_relation"),
    ]

    operations = [
        migrations.AddField(
            model_name="changerecord",
            name="content_hash",
            field=models.CharField(blank=True, default="", max_length=64, verbose_name="核实内容哈希"),
        ),
    ]
