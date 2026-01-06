from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('monitor', '0021_monitorplugin_is_pre'),
    ]

    operations = [
        migrations.AlterField(
            model_name='monitoralertmetricsnapshot',
            name='alert',
            field=models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to='monitor.monitoralert', verbose_name='关联告警'),
        ),
    ]
