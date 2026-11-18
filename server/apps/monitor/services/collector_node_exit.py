from collections import defaultdict

from django.db import transaction
from django.db.models import Q

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import monitor_logger as logger
from apps.core.logger import safe_log_value
from apps.monitor.models import CollectConfig, MonitorInstance
from apps.monitor.services.monitor_instance_removal import MonitorInstanceRemovalService
from apps.rpc.node_mgmt import NodeMgmt

MONITOR_EXIT_FINISHED_LOG = "monitor collector node exit finished node_id=%s linked_count=%s config_count=%s"
MONITOR_RETURN_FINISHED_LOG = "monitor collector node returned node_id=%s config_count=%s host_instance_id=%s"
HOST_AGENT_COLLECTOR = "Telegraf"
HOST_AGENT_COLLECT_TYPE = "host"


class MonitorCollectorNodeExit:
    """节点退出时保留联动主机，只清 node_id，并给本次配置写下已删除节点快照。"""

    @classmethod
    def on_node_removed(cls, node, config_ids, operator):
        normalized_ids = [str(item) for item in config_ids if item]
        linked_ids = []
        with transaction.atomic():
            linked_ids = cls._linked_instance_ids(node)
            if linked_ids:
                MonitorInstance.objects.filter(id__in=linked_ids).update(node_id=None)
            if normalized_ids:
                CollectConfig.objects.filter(id__in=normalized_ids).update(
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

    @classmethod
    def on_node_returned(cls, node, organization_ids):
        """同一节点 ID 回来后，把该节点名下的停采配置挂回，并写回主机 node_id。"""
        configs = list(
            CollectConfig.objects.filter(
                executor_node_id=node.id,
                executor_node_removed=True,
            )
        )
        if not configs:
            return None
        grouped = defaultdict(list)
        for config in configs:
            grouped[config.monitor_instance_id].append(config)
        host_ids = set(
            CollectConfig.objects.filter(
                monitor_instance_id__in=list(grouped),
                collector=HOST_AGENT_COLLECTOR,
                collect_type=HOST_AGENT_COLLECT_TYPE,
            ).values_list("monitor_instance_id", flat=True)
        )
        org_ids = list(organization_ids or [])
        node_mgmt = NodeMgmt(is_local_client=True)
        returned_host_id = None
        for instance_id, instance_configs in grouped.items():
            config_ids = [config.id for config in instance_configs]
            owner_ids = list(CollectConfig.objects.filter(monitor_instance_id=instance_id).values_list("id", flat=True))
            node_mgmt.move_child_configs_to_node(config_ids, node.id, owner_ids, org_ids)
            CollectConfig.objects.filter(id__in=config_ids).update(
                executor_node_removed=False,
                executor_node_id="",
                executor_node_name="",
            )
            if instance_id in host_ids:
                MonitorInstance.objects.filter(id=instance_id).update(node_id=node.id)
                if returned_host_id is None or str(instance_id) < str(returned_host_id):
                    returned_host_id = instance_id
        logger.debug(
            MONITOR_RETURN_FINISHED_LOG,
            safe_log_value(node.id),
            len(configs),
            safe_log_value(returned_host_id),
        )
        return returned_host_id

    @staticmethod
    def _linked_instance_ids(node):
        query = Q(node_id=node.id)
        if node.monitor_id:
            query |= Q(id=node.monitor_id)
        return list(MonitorInstance.objects.filter(query).values_list("id", flat=True))

    @classmethod
    def clear(cls, instance_id):
        configs = list(cls._removed_configs(instance_id))
        config_ids = [config.id for config in configs]
        NodeMgmt(is_local_client=True).delete_owned_child_configs(config_ids)
        CollectConfig.objects.filter(id__in=config_ids).delete()

    @classmethod
    def reassign(cls, instance_id, node_id, permission_data=None):
        configs = list(cls._removed_configs(instance_id))
        target = cls._authorized_node(node_id, permission_data)
        config_ids = [config.id for config in configs]
        owner_ids = list(CollectConfig.objects.filter(monitor_instance_id=instance_id).values_list("id", flat=True))
        NodeMgmt(is_local_client=True).move_child_configs_to_node(
            config_ids,
            target["id"],
            owner_ids,
            list(target.get("organization_ids") or []),
        )
        CollectConfig.objects.filter(id__in=config_ids).update(
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

    @classmethod
    def _authorized_node(cls, node_id, permission_data):
        node_key = str(node_id or "").strip()
        authorized = NodeMgmt(is_local_client=True).get_authorized_nodes_by_ids([node_key], permission_data or {})
        for item in authorized or []:
            if isinstance(item, dict) and str(item.get("id")) == node_key:
                return item
        raise BaseAppException("采集节点不存在")
