from django.db.models import Q

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import log_logger as logger
from apps.core.logger import safe_log_value
from apps.log.models import CollectConfig, CollectInstance
from apps.node_mgmt.models.sidecar import Node

LOG_EXIT_FINISHED_LOG = "log collector node exit finished node_id=%s instance_count=%s"


class LogCollectorNodeExit:
    """节点退出时保留日志采集实例，只记录采集节点已删除。"""

    @classmethod
    def on_node_removed(cls, node, config_ids, operator):
        del operator
        normalized_ids = [str(item) for item in config_ids if item]
        instance_ids = set(CollectConfig.objects.filter(id__in=normalized_ids).values_list("collect_instance_id", flat=True))
        query = Q(node_id=node.id)
        if instance_ids:
            query |= Q(id__in=instance_ids)
        instances = list(CollectInstance.objects.filter(query))
        for instance in instances:
            instance.collector_node_removed = True
            instance.removed_collector_node_id = node.id
            instance.removed_collector_node_name = node.name or node.id
            instance.node_id = None
            instance.save(
                update_fields=[
                    "collector_node_removed",
                    "removed_collector_node_id",
                    "removed_collector_node_name",
                    "node_id",
                ]
            )
        logger.debug(LOG_EXIT_FINISHED_LOG, safe_log_value(node.id), len(instances))

    @classmethod
    def clear(cls, instance_id):
        instance = cls._removed_instance(instance_id)
        config_ids = list(CollectConfig.objects.filter(collect_instance=instance).values_list("id", flat=True))
        from apps.node_mgmt.services.node_collection_exit import NodeCollectionExitService

        NodeCollectionExitService.delete_owned_configs(config_ids)
        CollectConfig.objects.filter(collect_instance=instance).delete()
        instance.collector_node_removed = False
        instance.removed_collector_node_id = ""
        instance.removed_collector_node_name = ""
        instance.save(
            update_fields=[
                "collector_node_removed",
                "removed_collector_node_id",
                "removed_collector_node_name",
            ]
        )

    @classmethod
    def reassign(cls, instance_id, node_id):
        instance = cls._removed_instance(instance_id)
        target = Node.objects.filter(id=str(node_id or "").strip()).first()
        if target is None:
            raise BaseAppException("采集节点不存在")
        config_ids = list(CollectConfig.objects.filter(collect_instance=instance).values_list("id", flat=True))
        owner_ids = config_ids
        from apps.node_mgmt.services.node_collection_exit import NodeCollectionExitService

        NodeCollectionExitService.move_configs_to_node(config_ids, target, owner_ids)
        instance.node_id = target.id
        instance.collector_node_removed = False
        instance.removed_collector_node_id = ""
        instance.removed_collector_node_name = ""
        instance.save(
            update_fields=[
                "node_id",
                "collector_node_removed",
                "removed_collector_node_id",
                "removed_collector_node_name",
            ]
        )

    @staticmethod
    def _removed_instance(instance_id):
        instance = CollectInstance.objects.filter(id=instance_id).first()
        if instance is None:
            raise BaseAppException("采集实例不存在")
        if not instance.collector_node_removed:
            raise BaseAppException("采集节点未删除")
        return instance
