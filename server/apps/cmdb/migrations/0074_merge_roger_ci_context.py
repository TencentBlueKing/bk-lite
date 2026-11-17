# roger 的 0069_ci_context 与社区版 0073_merge_ci_context_and_repair 是两条叶子。
# 空操作节点收成一个 head，避免 migrate 报 multiple leaf nodes。
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("cmdb", "0069_ci_context"),
        ("cmdb", "0073_merge_ci_context_and_repair"),
    ]

    operations = []
