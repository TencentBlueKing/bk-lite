# 该迁移历史上在 cmdb 内创建过自定义报表相关表，自定义报表能力后续整体迁移至
# cmdb_enterprise 应用（独立表前缀，与 cmdb 无冲突），故此处保留为空操作 stub：
#   - 旧版库已应用本迁移并建有相关表 —— 保留同名节点使其历史一致，且不回删表；
#   - 新版 / 全新库不再需要这些表，空操作即可，不会产生孤儿模型或多余表。
# 详见同目录 0025_merge / 0027_merge_reconcile_history 的历史收敛说明。
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('cmdb', '0023_collecttaskcredentialhit_and_more'),
    ]

    operations = [
    ]
