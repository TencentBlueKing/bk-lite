from functools import partial

from apps.cmdb.collection.collect_plugin.middleware import MiddlewareCollectMetrics
from apps.cmdb.collection.plugins.community.middleware.base import BaseMiddlewareCollectionPlugin


class OpenrestyCollectionPlugin(BaseMiddlewareCollectionPlugin):
    supported_model_id = "openresty"
    metric_names = ("openresty_info_gauge",)
    field_mapping = {
        "inst_name": MiddlewareCollectMetrics.get_inst_name,
        "ip_addr": "ip_addr",
        "port": MiddlewareCollectMetrics.get_port,
        "version": "version",
        "openresty_path": "openresty_path",
        "log_path": "log_path",
        "config_path": partial(MiddlewareCollectMetrics.pick_value, keys=("config_path", "conf_path")),
        "doc_root": "doc_root",
        "assos": MiddlewareCollectMetrics.get__host_assos,
    }
