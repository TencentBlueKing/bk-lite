from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("cmdb", "0058_customcollectplugin"),
    ]

    operations = [
        migrations.AlterField(
            model_name="collectmodels",
            name="task_type",
            field=models.CharField(
                choices=[
                    ("vm", "VM采集"),
                    ("snmp", "SNMP采集"),
                    ("k8s", "K8S采集"),
                    ("cloud", "云采集"),
                    ("protocol", "协议采集"),
                    ("host", "主机采集"),
                    ("db", "数据库采集"),
                    ("middleware", "中间件采集"),
                    ("config_file", "配置文件采集"),
                    ("ip", "IP采集"),
                    ("other", "其他采集"),
                    ("custom_script", "自定义脚本采集"),
                ],
                help_text="任务类型",
                max_length=32,
            ),
        ),
    ]
