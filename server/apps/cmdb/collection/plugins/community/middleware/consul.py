from apps.cmdb.collection.collect_plugin.middleware import MiddlewareCollectMetrics
from apps.cmdb.collection.plugins.community.middleware.base import BaseMiddlewareCollectionPlugin


class ConsulCollectionPlugin(BaseMiddlewareCollectionPlugin):
    supported_model_id = "consul"
    metric_names = ("consul_info_gauge",)
    field_mapping = {
        "inst_name": MiddlewareCollectMetrics.get_inst_name,
        "ip_addr": "ip_addr",
        "port": "port",
        "install_path": "install_path",
        "version": "version",
        "data_dir": "data_dir",
        "conf_path": "conf_path",
        "role": "role",
    }
