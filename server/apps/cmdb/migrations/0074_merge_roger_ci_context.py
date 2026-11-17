# 以 master 的 0073 链为准，把 roger 残留的 0069_ci_context 叶子收进来。
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("cmdb", "0069_ci_context"),
        ("cmdb", "0073_merge_ci_context_and_repair"),
    ]

    operations = []
