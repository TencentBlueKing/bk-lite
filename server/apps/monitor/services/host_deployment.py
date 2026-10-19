from apps.monitor.models import CollectConfig
from apps.rpc.node_mgmt import NodeMgmt


class HostDeploymentStatus:
    """集中查询节点当前是否已经下发主机监控。"""

    MONITOR_OBJECT_NAME = "Host"
    COLLECTOR = "Telegraf"
    COLLECT_TYPE = "host"

    def __init__(self, node_mgmt=None):
        self._node_mgmt = node_mgmt or NodeMgmt()

    @classmethod
    def applies_to(cls, monitor_object_name, collector, collect_type):
        return monitor_object_name == cls.MONITOR_OBJECT_NAME and collector == cls.COLLECTOR and collect_type == cls.COLLECT_TYPE

    @classmethod
    def sink_child_config(cls):
        """节点列表在数据源侧将已接入主机监控的节点整块沉底。"""
        return {"collector": cls.COLLECTOR, "collect_type": cls.COLLECT_TYPE}

    def get_configured_node_ids(self, node_ids):
        live_ids, _unbound_ids = self._partition_child_configs(node_ids)
        return live_ids

    def get_unbound_child_config_ids(self, node_ids):
        _live_ids, unbound_ids = self._partition_child_configs(node_ids)
        return unbound_ids

    def release_unbound_child_configs(self, node_ids):
        unbound_ids = self.get_unbound_child_config_ids(node_ids)
        if unbound_ids:
            self._node_mgmt.delete_child_configs(unbound_ids)
        return unbound_ids

    def _partition_child_configs(self, node_ids):
        normalized_node_ids = list(dict.fromkeys(str(node_id) for node_id in node_ids if node_id not in (None, "")))
        if not normalized_node_ids:
            return set(), []

        assignments = (
            self._node_mgmt.get_child_config_assignments(
                normalized_node_ids,
                self.COLLECTOR,
                self.COLLECT_TYPE,
            )
            or []
        )
        child_ids = []
        normalized_assignments = []
        seen_child_ids = set()
        for item in assignments:
            child_id = str((item or {}).get("id") or "").strip()
            node_id = str((item or {}).get("node_id") or "").strip()
            if not child_id or not node_id:
                continue
            normalized_assignments.append({"id": child_id, "node_id": node_id})
            if child_id not in seen_child_ids:
                seen_child_ids.add(child_id)
                child_ids.append(child_id)
        live_host_ids, protected_ids = self._live_child_config_ids(child_ids)
        configured_node_ids = {item["node_id"] for item in normalized_assignments if item["id"] in live_host_ids}
        unbound_ids = [child_id for child_id in child_ids if child_id not in protected_ids]
        return configured_node_ids, unbound_ids

    @classmethod
    def _live_child_config_ids(cls, child_ids):
        if not child_ids:
            return set(), set()
        rows = CollectConfig.objects.filter(
            id__in=child_ids,
            monitor_instance__is_deleted=False,
        ).values_list("id", "monitor_instance__monitor_object__name")
        protected_ids = set()
        live_host_ids = set()
        for config_id, object_name in rows:
            collect_id = str(config_id)
            protected_ids.add(collect_id)
            if object_name == cls.MONITOR_OBJECT_NAME:
                live_host_ids.add(collect_id)
        return live_host_ids, protected_ids
