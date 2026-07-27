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
        return (
            monitor_object_name == cls.MONITOR_OBJECT_NAME
            and collector == cls.COLLECTOR
            and collect_type == cls.COLLECT_TYPE
        )

    def get_configured_node_ids(self, node_ids):
        normalized_node_ids = list(
            dict.fromkeys(str(node_id) for node_id in node_ids if node_id not in (None, ""))
        )
        if not normalized_node_ids:
            return set()

        configured_node_ids = self._node_mgmt.get_nodes_with_child_config(
            normalized_node_ids,
            self.COLLECTOR,
            self.COLLECT_TYPE,
        )
        return {str(node_id) for node_id in configured_node_ids}
