from apps.cmdb.collection.collect_plugin.middleware import MiddlewareCollectMetrics
from apps.cmdb.collection.plugins.community.middleware.base import BaseMiddlewareCollectionPlugin


class TomcatCollectionPlugin(BaseMiddlewareCollectionPlugin):
    supported_model_id = "tomcat"
    metric_names = ("tomcat_info_gauge",)
    field_mapping = {
        "inst_name": MiddlewareCollectMetrics.get_inst_name,
        "ip_addr": "ip_addr",
        "port": "port",
        "catalina_path": "catalina_path",
        "version": "version",
        "xms": "xms",
        "xmx": "xmx",
        "max_perm_size": "max_perm_size",
        "permsize": "permsize",
        "log_path": "log_path",
        "java_version": "java_version",
    }
