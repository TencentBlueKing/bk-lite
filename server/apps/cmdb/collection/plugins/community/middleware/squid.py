from apps.cmdb.collection.collect_plugin.middleware import MiddlewareCollectMetrics
from apps.cmdb.collection.plugins.community.middleware.base import BaseMiddlewareCollectionPlugin


class SquidCollectionPlugin(BaseMiddlewareCollectionPlugin):
    supported_model_id = "squid"
    metric_names = ("squid_info_gauge",)
    field_mapping = {
        "inst_name": MiddlewareCollectMetrics.get_inst_name,
        "ip_addr": "ip_addr",
        "port": MiddlewareCollectMetrics.get_port,
        "version": "version",
        "install_path": "install_path",
        "config_file_path": "config_file_path",
        "cache_dir": "cache_dir",
        "access_log": "access_log",
        "error_log": "error_log",
        "visible_hostname": "visible_hostname",
    }
