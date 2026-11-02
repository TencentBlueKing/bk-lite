# 社区版从 0036 写出提醒世代和升级周期；本分支从同一节点写出 ITSM 工单。
# 空操作节点把两条叶子收成一个 head，避免 migrate 报 multiple leaf nodes。
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("alerts", "0038_alertescalationtask_cycle"),
        ("alerts", "0039_itsm_comment_error"),
    ]

    operations = []
