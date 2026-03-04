# -- coding: utf-8 --
# Redis 模型新增拓扑相关属性（适配新采集脚本输出：topo_mode, cluster_uuid, slaves, master）
from django.core.management.base import BaseCommand

from apps.cmdb.services.model import ModelManage
from apps.core.exceptions.base_app_exception import BaseAppException


REDIS_MODEL_ID = "redis"

# 与计划书、databases.py model_field_mapping 一致
REDIS_TOPO_ATTRS = [
    {
        "attr_id": "topo_mode",
        "attr_name": "拓扑模式",
        "attr_type": "str",
        "is_only": False,
        "is_required": False,
        "editable": True,
        "option": {},
        "attr_group": "default",
        "user_prompt": "standalone/replication/sentinel/cluster",
    },
    {
        "attr_id": "cluster_uuid",
        "attr_name": "集群/哨兵组标识",
        "attr_type": "str",
        "is_only": False,
        "is_required": False,
        "editable": True,
        "option": {},
        "attr_group": "default",
        "user_prompt": "集群或哨兵组唯一标识",
    },
    {
        "attr_id": "slaves",
        "attr_name": "从节点列表",
        "attr_type": "str",
        "is_only": False,
        "is_required": False,
        "editable": True,
        "option": {},
        "attr_group": "default",
        "user_prompt": "从节点信息（JSON 字符串）",
    },
    {
        "attr_id": "master",
        "attr_name": "主节点引用",
        "attr_type": "str",
        "is_only": False,
        "is_required": False,
        "editable": True,
        "option": {},
        "attr_group": "default",
        "user_prompt": "主节点信息（JSON 字符串）",
    },
]


class Command(BaseCommand):
    help = "为 Redis 模型添加拓扑相关属性（topo_mode, cluster_uuid, slaves, master）"

    def handle(self, *args, **options):
        model_info = ModelManage.search_model_info(REDIS_MODEL_ID)
        if not model_info:
            self.stdout.write(self.style.WARNING(f"模型 {REDIS_MODEL_ID} 不存在，跳过"))
            return

        existing = {a["attr_id"] for a in ModelManage.search_model_attr(REDIS_MODEL_ID)}
        added = 0
        for attr_info in REDIS_TOPO_ATTRS:
            attr_id = attr_info["attr_id"]
            if attr_id in existing:
                self.stdout.write(f"  已有属性: {attr_id}")
                continue
            try:
                ModelManage.create_model_attr(REDIS_MODEL_ID, attr_info, username="system")
                self.stdout.write(self.style.SUCCESS(f"  已添加: {attr_id}"))
                added += 1
            except BaseAppException as e:
                self.stdout.write(self.style.ERROR(f"  添加 {attr_id} 失败: {e.message}"))

        self.stdout.write(self.style.SUCCESS(f"完成，新增 {added} 个属性"))
