from apps.node_mgmt.constants.controller import ControllerConstants
from apps.node_mgmt.models.sidecar import Node
from django.core.management import BaseCommand
from apps.core.logger import node_logger as logger
from apps.node_mgmt.services.sidecar import Sidecar
from apps.node_mgmt.tasks.action_task import converge_collector_action_task_for_node
from apps.node_mgmt.utils.sidecar import format_tags_dynamic
from apps.node_mgmt.utils.architecture import normalize_cpu_architecture


class Command(BaseCommand):
    help = "修复节点默认配置"

    @classmethod
    def _reconcile_default_pre_configs_for_architecture(cls, node):
        node_arch = normalize_cpu_architecture(getattr(node, "cpu_architecture", ""))
        if not node_arch:
            return

        selected_collectors = Sidecar._get_default_collectors_for_node(node)
        if not selected_collectors:
            return

        expected_names = [f"{collector_name}-{node.id}" for collector_name in selected_collectors.keys()]
        default_configs = node.collectorconfiguration_set.filter(is_pre=True, name__in=expected_names).select_related("collector")

        for config in default_configs:
            desired_collector = selected_collectors.get(config.collector.name)
            if not desired_collector or config.collector_id == desired_collector.id:
                continue

            logger.info(
                "Rebinding default configuration %s for node %s from collector %s to %s after cpu_architecture=%s",
                config.id,
                node.id,
                config.collector_id,
                desired_collector.id,
                node_arch,
            )
            config.collector = desired_collector
            config.save(update_fields=["collector"])

    def handle(self, *args, **options):
        logger.info("开始修复节点默认配置...")
        nodes = Node.objects.all()
        for node in nodes:
            try:
                # 处理标签数据
                allowed_prefixes = [ControllerConstants.NODE_TYPE_TAG]
                tags_data = format_tags_dynamic(node.tags, allowed_prefixes)
                node_types = tags_data.get(ControllerConstants.NODE_TYPE_TAG, [])
                self._reconcile_default_pre_configs_for_architecture(node)
                Sidecar.create_default_config(node, node_types)
                converge_collector_action_task_for_node.delay(node.id)
            except Exception as e:
                logger.error(f"修复节点 {node.id} 默认配置失败: {e}")
        logger.info("修复节点默认配置完成...")
