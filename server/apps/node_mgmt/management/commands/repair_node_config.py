from apps.node_mgmt.constants.controller import ControllerConstants
from apps.node_mgmt.models.sidecar import Node
from django.core.management import BaseCommand
from apps.core.logger import node_logger as logger
from apps.node_mgmt.services.sidecar import Sidecar
from apps.node_mgmt.utils.sidecar import format_tags_dynamic


class Command(BaseCommand):
    help = "修复节点默认配置"

    def handle(self, *args, **options):
        logger.info("开始修复节点默认配置...")
        nodes = Node.objects.all()
        for node in nodes:
            try:
                # 处理标签数据
                allowed_prefixes = [ControllerConstants.NODE_TYPE_TAG]
                tags_data = format_tags_dynamic(node.tags, allowed_prefixes)
                node_types = tags_data.get(ControllerConstants.NODE_TYPE_TAG, [])
                Sidecar.create_default_config(node, node_types)
            except Exception as e:
                logger.error(f"修复节点 {node.id} 默认配置失败: {e}")
        logger.info("修复节点默认配置完成...")
