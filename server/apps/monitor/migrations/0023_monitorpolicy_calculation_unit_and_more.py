# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('monitor', '0022_alter_monitoralertmetricsnapshot_alert'),
    ]

    operations = [
        migrations.AddField(
            model_name='monitorpolicy',
            name='metric_unit',
            field=models.CharField(blank=True, default='', max_length=50, verbose_name='指标原始单位'),
        ),
        migrations.AddField(
            model_name='monitorpolicy',
            name='calculation_unit',
            field=models.CharField(blank=True, default='', max_length=50, verbose_name='计算单位（用于阈值对比和结果记录）'),
        ),
    ]
