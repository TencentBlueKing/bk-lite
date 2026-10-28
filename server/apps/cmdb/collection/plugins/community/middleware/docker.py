from apps.cmdb.collection.collect_plugin.middleware import MiddlewareCollectMetrics
from apps.cmdb.collection.plugins.community.middleware.base import BaseMiddlewareCollectionPlugin


class DockerCollectionPlugin(BaseMiddlewareCollectionPlugin):
    supported_model_id = "docker"
    metric_names = ("docker_info_gauge",)

    def format_port(self, data):
        return data.get("port") or self._extract_primary_port(data)

    def format_networks(self, data):
        return self.format_json_field(data.get("networks"))

    def format_mounts(self, data):
        return self.format_json_field(data.get("mounts"))

    field_mapping = {
        "inst_name": MiddlewareCollectMetrics.get_docker_inst_name,
        "ip_addr": MiddlewareCollectMetrics.get_ip_addr,
        "port": format_port,
        "container_id": "container_id",
        "status": "status",
        "command": "command",
        "created": "created",
        "image": "image",
        "networks": format_networks,
        "ports": "ports",
        "mounts": format_mounts,
    }
