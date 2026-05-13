from apps.cmdb.collection.collect_plugin.middleware import MiddlewareCollectMetrics
from apps.cmdb.collection.plugins.community.middleware.base import BaseMiddlewareCollectionPlugin


class TongwebCollectionPlugin(BaseMiddlewareCollectionPlugin):
    supported_model_id = "tongweb"
    metric_names = ("tongweb_info_gauge",)
    field_mapping = {
        "inst_name": MiddlewareCollectMetrics.get_inst_name,
        "ip_addr": "ip_addr",
        "port": "port",
        "version": "version",
        "bin_path": "bin_path",
        "log_path": "log_path",
        "java_version": "java_version",
        "xms": "xms",
        "xmx": "xmx",
        "metaspace_size": "metaspace_size",
        "max_metaspace_size": "max_metaspace_size",
    }
