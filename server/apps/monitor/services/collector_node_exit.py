from django.db.models import Q

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import monitor_logger as logger
from apps.core.logger import safe_log_value
from apps.monitor.models import CollectConfig, MonitorInstance
from apps.monitor.services.monitor_instance_removal import MonitorInstanceRemovalService
from apps.node_mgmt.models.sidecar import Node

MONITOR_EXIT_FINISHED_LOG = "monitor collector node exit finished node_id=%s linked_count=%s config_count=%s"


class MonitorCollectorNodeExit:
    """节点退出时软退役联动主机，并标记监控自己创建的采集配置。"""

    @classmethod
    def on_node_removed(cls, node, config_ids, operator):
        linked_ids = cls._linked_instance_ids(node)
        if linked_ids:
            for instance in MonitorInstance.objects.filter(id__in=linked_ids):
                instance.is_deleted = True
                instance.is_active = False
                instance.node_id = None
                instance.save(update_fields=["is_deleted", "is_active", "node_id"])
        normalized_ids = [str(item) for item in config_ids if item]
        if normalized_ids:
            CollectConfig.objects.filter(id__in=normalized_ids).exclude(monitor_instance_id__in=linked_ids).update(
                executor_node_removed=True,
                executor_node_id=node.id,
                executor_node_name=node.name or node.id,
            )
        if linked_ids:
            MonitorInstanceRemovalService.close_alerts_for_instances(
                linked_ids,
                operator=operator or "system",
                reason="linked_node_removed",
            )
        logger.debug(
            MONITOR_EXIT_FINISHED_LOG,
            safe_log_value(node.id),
            len(linked_ids),
            len(normalized_ids),
        )

    @staticmethod
    def _linked_instance_ids(node):
        query = Q(node_id=node.id)
        if node.monitor_id:
            query |= Q(id=node.monitor_id)
        return list(MonitorInstance.objects.filter(query).values_list("id", flat=True))

    @classmethod
    def clear(cls, instance_id):
        configs = list(cls._removed_configs(instance_id))
        from apps.node_mgmt.services.node_collection_exit import NodeCollectionExitService

        NodeCollectionExitService.delete_owned_configs([config.id for config in configs])
        CollectConfig.objects.filter(id__in=[config.id for config in configs]).delete()

    @classmethod
    def reassign(cls, instance_id, node_id):
        target = cls._target_node(node_id)
        configs = list(cls._removed_configs(instance_id))
        owner_ids = CollectConfig.objects.filter(monitor_instance_id=instance_id).values_list("id", flat=True)
        from apps.node_mgmt.services.node_collection_exit import NodeCollectionExitService

        NodeCollectionExitService.move_configs_to_node([config.id for config in configs], target, owner_ids)
        CollectConfig.objects.filter(id__in=[config.id for config in configs]).update(
            executor_node_removed=False,
            executor_node_id="",
            executor_node_name="",
        )

    @staticmethod
    def _removed_configs(instance_id):
        configs = list(CollectConfig.objects.filter(monitor_instance_id=instance_id, executor_node_removed=True))
        if not configs:
            raise BaseAppException("没有已删除采集节点的配置")
        return configs

    @staticmethod
    def _target_node(node_id):
        node = Node.objects.filter(id=str(node_id or "").strip()).first()
        if node is None:
            raise BaseAppException("采集节点不存在")
        return node
