from apps.cmdb.collection.collect_plugin.middleware import MiddlewareCollectMetrics
from apps.cmdb.collection.plugins.community.middleware.base import BaseMiddlewareCollectionPlugin


class EtcdCollectionPlugin(BaseMiddlewareCollectionPlugin):
    supported_model_id = "etcd"
    metric_names = ("etcd_info_gauge",)
    field_mapping = {
        "inst_name": MiddlewareCollectMetrics.get_inst_name,
        "ip_addr": "ip_addr",
        "port": "port",
        "version": "version",
        "data_dir": "data_dir",
        "conf_file_path": "conf_file_path",
        "peer_port": "peer_port",
        "install_path": "install_path",
    }
