from apps.cmdb.collection.collect_plugin.middleware import MiddlewareCollectMetrics
from apps.cmdb.collection.plugins.community.middleware.base import BaseMiddlewareCollectionPlugin


class ActivemqCollectionPlugin(BaseMiddlewareCollectionPlugin):
    supported_model_id = "activemq"
    metric_names = ("activemq_info_gauge",)
    field_mapping = {
        "inst_name": MiddlewareCollectMetrics.get_inst_name,
        "ip_addr": "ip_addr",
        "port": "port",
        "version": "version",
        "install_path": "install_path",
        "conf_path": "conf_path",
        "java_path": "java_path",
        "java_version": "java_version",
        "xms": "xms",
        "xmx": "xmx",
    }
