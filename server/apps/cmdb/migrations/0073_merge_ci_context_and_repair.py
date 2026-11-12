# 社区版在 0069 之后增加 CI 上下文表；
# 本分支在同一祖先上增加实例修复断点和节点同步摘要，并由 0072 收口。
# 空操作节点把两条叶子收成一个 head，避免 migrate 报 multiple leaf nodes。
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("cmdb", "0070_ci_context"),
        ("cmdb", "0072_merge_repair_state_and_node_sync"),
    ]

    operations = []
