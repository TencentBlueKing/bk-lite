# 以 master 为准：CI 上下文表由 0070_ci_context 创建。
# 本文件只保留 roger 已用过的编号，避免已 migrate 的库找不到节点。
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("cmdb", "0068_alter_changerecord_scenario"),
    ]

    operations = []
