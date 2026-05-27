from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cmdb", "0018_nodemgmtsyncconfig_collectmodels_is_system_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="collectmodels",
            name="exec_status",
            field=models.PositiveSmallIntegerField(
                choices=[
                    (0, "未执行"),
                    (1, "正在采集"),
                    (2, "成功"),
                    (3, "异常"),
                    (4, "超时"),
                    (5, "正在写入"),
                    (6, "强制终止"),
                    (8, "部分成功"),
                ],
                default=0,
                help_text="执行状态",
            ),
        ),
    ]
