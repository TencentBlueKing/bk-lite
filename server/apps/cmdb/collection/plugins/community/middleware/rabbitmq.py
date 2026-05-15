from apps.cmdb.collection.collect_plugin.middleware import MiddlewareCollectMetrics
from apps.cmdb.collection.plugins.community.middleware.base import BaseMiddlewareCollectionPlugin


class RabbitmqCollectionPlugin(BaseMiddlewareCollectionPlugin):
    supported_model_id = "rabbitmq"
    metric_names = ("rabbitmq_info_gauge",)
    field_mapping = {
        "inst_name": MiddlewareCollectMetrics.get_inst_name,
        "ip_addr": "ip_addr",
        "port": "port",
        "allport": "allport",
        "node_name": "node_name",
        "log_path": "log_path",
        "conf_path": "conf_path",
        "version": "version",
        "enabled_plugin_file": "enabled_plugin_file",
        "erlang_version": "erlang_version",
    }
