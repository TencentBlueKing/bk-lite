# 社区版在 0061 之后追加扫描进度、端口指纹、进程指纹和命中证据；
# 本分支在同一祖先上追加采集调和，并让自动关联待重算表直接依赖 0060。
# 空操作节点把三条叶子收成一个 head，避免 migrate 报 multiple leaf nodes。
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("cmdb", "0062_collect_reconcile"),
        ("cmdb", "0063_auto_relation_pending"),
        ("cmdb", "0065_scanhit_confidence_evidence"),
    ]

    operations = []
