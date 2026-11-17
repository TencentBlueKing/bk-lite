# roger 在 0068 之后先建了 CI 上下文表。社区版同一张表落在 0070_ci_context。
# 本文件保留编号，避免已 migrate 的 roger 库丢记录；DDL 交给 0070，库里已有表则跳过。
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("cmdb", "0068_alter_changerecord_scenario"),
    ]

    operations = []
