from functools import partial

from apps.cmdb.collection.collect_plugin.middleware import MiddlewareCollectMetrics
from apps.cmdb.collection.plugins.community.middleware.base import BaseMiddlewareCollectionPlugin


class NginxCollectionPlugin(BaseMiddlewareCollectionPlugin):
    supported_model_id = "nginx"
    metric_names = ("nginx_info_gauge",)
    field_mapping = {
        "ip_addr": "ip_addr",
        "port": partial(MiddlewareCollectMetrics.pick_value, keys=("port", "listen_port")),
        "bin_path": partial(MiddlewareCollectMetrics.pick_value, keys=("bin_path", "nginx_path")),
        "version": "version",
        "log_path": "log_path",
        "conf_path": partial(MiddlewareCollectMetrics.pick_value, keys=("conf_path", "config_path")),
        "server_name": "server_name",
        "include": "include",
        "ssl_version": "ssl_version",
        "inst_name": MiddlewareCollectMetrics.get_inst_name,
    }
