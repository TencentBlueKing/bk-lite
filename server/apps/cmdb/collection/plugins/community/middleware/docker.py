from apps.cmdb.collection.collect_plugin.middleware import MiddlewareCollectMetrics
from apps.cmdb.collection.plugins.community.middleware.base import BaseMiddlewareCollectionPlugin


class DockerCollectionPlugin(BaseMiddlewareCollectionPlugin):
    supported_model_id = "docker"
    metric_names = ("docker_info_gauge",)
    field_mapping = {
        "inst_name": MiddlewareCollectMetrics.get_docker_inst_name,
        "ip_addr": MiddlewareCollectMetrics.get_ip_addr,
        "port": lambda self, data: data.get("port") or self._extract_primary_port(data),
        "container_id": "container_id",
        "status": "status",
        "command": "command",
        "created": "created",
        "image": "image",
        "networks": lambda self, data: self.format_json_field(data.get("networks")),
        "ports": "ports",
        "mounts": lambda self, data: self.format_json_field(data.get("mounts")),
    }
