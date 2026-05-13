from apps.cmdb.collection.collect_plugin.middleware import MiddlewareCollectMetrics
from apps.cmdb.collection.plugins.community.middleware.base import BaseMiddlewareCollectionPlugin


class JbossCollectionPlugin(BaseMiddlewareCollectionPlugin):
    supported_model_id = "jboss"
    metric_names = ("jboss_info_gauge",)
    field_mapping = {
        "inst_name": MiddlewareCollectMetrics.get_inst_name,
        "ip_addr": "ip_addr",
        "port": MiddlewareCollectMetrics.get_port,
        "version": "version",
        "install_path": "install_path",
        "jvm_xms": "jvm_xms",
        "jvm_xmx": "jvm_xmx",
        "role": "role",
        "config_file": "config_file",
    }
