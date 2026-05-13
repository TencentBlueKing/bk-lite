from apps.cmdb.collection.collect_plugin.middleware import MiddlewareCollectMetrics
from apps.cmdb.collection.plugins.community.middleware.base import BaseMiddlewareCollectionPlugin


class MemcachedCollectionPlugin(BaseMiddlewareCollectionPlugin):
    supported_model_id = "memcached"
    metric_names = ("memcached_info_gauge",)
    field_mapping = {
        "inst_name": MiddlewareCollectMetrics.get_inst_name,
        "ip_addr": "ip_addr",
        "port": MiddlewareCollectMetrics.get_port,
        "version": "version",
        "install_path": "install_path",
        "maxconn": "maxconn",
        "cachesize": "cachesize",
        "user_name": "user_name",
    }
