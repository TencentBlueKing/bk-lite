import uuid

from django.db import transaction

from apps.core.logger import node_mgmt_logger as logger
from apps.core.logger import safe_exception_info, safe_log_value
from apps.node_mgmt.models.sidecar import ChildConfig, CollectorConfiguration, NodeCollectorConfiguration
from apps.node_mgmt.services.sidecar_cache import invalidate_configuration_etag

EXIT_FINISHED_LOG = "node collection exit finished node_id=%s config_count=%s"
EXIT_FAILED_LOG = "node collection exit failed node_id=%s failed_stage=%s error_type=%s"


def log_collection_exit_failure(node_id, stage, exc):
    logger.error(
        EXIT_FAILED_LOG,
        safe_log_value(node_id),
        stage,
        type(exc).__name__,
        exc_info=safe_exception_info(exc),
    )


class NodeCollectionExitService:
    """删除或卸载节点时，保留采集正文，并让默认父配置名让出。"""

    @classmethod
    def apply(cls, node, operator="system"):
        assignments = list(NodeCollectorConfiguration.objects.filter(node=node).select_related("collector_config__collector"))
        parent_ids = [row.collector_config_id for row in assignments]
        shared_parent_ids = set(
            NodeCollectorConfiguration.objects.filter(collector_config_id__in=parent_ids)
            .exclude(node_id=node.id)
            .values_list("collector_config_id", flat=True)
        )
        exclusive_parent_ids = [parent_id for parent_id in parent_ids if parent_id not in shared_parent_ids]
        child_ids = list(ChildConfig.objects.filter(collector_config_id__in=exclusive_parent_ids).values_list("id", flat=True))
        config_ids = list(dict.fromkeys([*exclusive_parent_ids, *child_ids]))
        cls._notify_monitor(node, config_ids, operator)
        cls._notify_log(node, config_ids, operator)
        cls._release_default_parent_names(assignments, node)
        logger.info(EXIT_FINISHED_LOG, safe_log_value(node.id), len(config_ids))

    @staticmethod
    def _notify_monitor(node, config_ids, operator):
        try:
            from apps.monitor.services.collector_node_exit import MonitorCollectorNodeExit

            MonitorCollectorNodeExit.on_node_removed(node, config_ids, operator)
        except Exception as exc:
            log_collection_exit_failure(node.id, "monitor", exc)

    @staticmethod
    def _notify_log(node, config_ids, operator):
        try:
            from apps.log.services.collector_node_exit import LogCollectorNodeExit

            LogCollectorNodeExit.on_node_removed(node, config_ids, operator)
        except Exception as exc:
            log_collection_exit_failure(node.id, "log", exc)

    @staticmethod
    def _release_default_parent_names(assignments, node):
        for row in assignments:
            parent = row.collector_config
            collector = parent.collector
            if collector is None or parent.name != f"{collector.name}-{node.id}":
                continue
            parent.name = f"detached-{parent.id}"[:100]
            parent.save(update_fields=["name"])

    @classmethod
    def delete_owned_configs(cls, config_ids):
        requested = [str(item) for item in config_ids if item]
        if not requested:
            return
        with transaction.atomic():
            ChildConfig.objects.filter(id__in=requested).delete()
            for parent in CollectorConfiguration.objects.filter(id__in=requested):
                if ChildConfig.objects.filter(collector_config_id=parent.id).exists():
                    continue
                parent.delete()

    @classmethod
    def move_configs_to_node(cls, config_ids, target_node, owner_config_ids):
        owner_ids = {str(item) for item in owner_config_ids}
        requested = [str(item) for item in config_ids if item]
        if not requested:
            return
        with transaction.atomic():
            children = list(ChildConfig.objects.select_related("collector_config__collector").filter(id__in=requested))
            child_ids = {child.id for child in children}
            for child in children:
                parent = child.collector_config
                if parent.nodes.filter(id=target_node.id).exists() and not cls._parent_has_other_owners(parent, owner_ids):
                    continue
                replacement = cls._parent_bound_to_node(target_node, parent.collector)
                if child.collector_config_id != replacement.id:
                    previous_parent_id = child.collector_config_id
                    child.collector_config = replacement
                    child.save(update_fields=["collector_config"])
                    invalidate_configuration_etag(previous_parent_id)
            parents = CollectorConfiguration.objects.select_related("collector").filter(id__in=[item for item in requested if item not in child_ids])
            for parent in parents:
                if cls._parent_has_other_owners(parent, owner_ids):
                    continue
                parent.nodes.add(target_node)

    @staticmethod
    def _parent_has_other_owners(parent, owner_ids):
        child_ids = ChildConfig.objects.filter(collector_config=parent).values_list("id", flat=True)
        return any(str(child_id) not in owner_ids for child_id in child_ids)

    @staticmethod
    def _parent_bound_to_node(node, collector):
        existing = CollectorConfiguration.objects.filter(collector=collector, nodes=node).order_by("-is_pre", "id").first()
        if existing is not None:
            return existing
        base_name = f"{collector.name}-{node.id}"[:100]
        name = base_name
        if CollectorConfiguration.objects.filter(name=name).exists():
            name = f"{collector.name}-{node.id}-{uuid.uuid4().hex[:8]}"[:100]
        created = CollectorConfiguration.objects.create(
            name=name,
            collector=collector,
            cloud_region=node.cloud_region,
            config_template="",
            is_pre=True,
        )
        created.nodes.add(node)
        return created
