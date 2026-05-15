from apps.cmdb.collection.collect_plugin.middleware import MiddlewareCollectMetrics
from apps.cmdb.collection.plugins.community.middleware.base import BaseMiddlewareCollectionPlugin


class ZookeeperCollectionPlugin(BaseMiddlewareCollectionPlugin):
    supported_model_id = "zookeeper"
    metric_names = ("zookeeper_info_gauge",)
    field_mapping = {
        "inst_name": MiddlewareCollectMetrics.get_inst_name,
        "ip_addr": "ip_addr",
        "port": "port",
        "version": "version",
        "install_path": "install_path",
        "log_path": "log_path",
        "conf_path": "conf_path",
        "java_path": "java_path",
        "java_version": "java_version",
        "data_dir": "data_dir",
        "tick_time": "tick_time",
        "init_limit": "init_limit",
        "sync_limit": "sync_limit",
        "server": "server",
    }
