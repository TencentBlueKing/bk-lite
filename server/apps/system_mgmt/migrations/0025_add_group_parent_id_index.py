"""
为 Group.parent_id 添加数据库索引，优化组织树查询性能。

注意事项：
- 如果 Group 表数据量较大（>100万行），建议在低峰期执行迁移
- PostgreSQL 可考虑使用 CONCURRENTLY 选项避免锁表
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("system_mgmt", "0024_init_builtin_nats_channel"),
    ]

    operations = [
        migrations.AlterField(
            model_name="group",
            name="parent_id",
            field=models.IntegerField(db_index=True, default=0),
        ),
        migrations.AlterField(
            model_name="channel",
            name="channel_type",
            field=models.CharField(
                choices=[
                    ("email", "Email"),
                    ("enterprise_wechat", "Enterprise Wechat"),
                    ("enterprise_wechat_bot", "Enterprise Wechat Bot"),
                    ("nats", "NATS"),
                ],
                max_length=30,
            ),
        ),
    ]
