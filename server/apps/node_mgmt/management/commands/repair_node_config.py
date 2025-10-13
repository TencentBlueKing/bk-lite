from apps.node_mgmt.models.sidecar import Node
from django.core.management import BaseCommand
from apps.core.logger import node_logger as logger
from apps.node_mgmt.services.sidecar import Sidecar


class Command(BaseCommand):
    help = "修复节点默认配置"

    def handle(self, *args, **options):
        logger.info("开始修复节点默认配置...")
        nodes = Node.objects.all()
        for node in nodes:
            try:
                Sidecar.create_default_config(node)
            except Exception as e:
                logger.error(f"修复节点 {node.id} 默认配置失败: {e}")
        logger.info("修复节点默认配置完成...")
