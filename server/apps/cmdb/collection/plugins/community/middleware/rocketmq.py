from functools import partial

from apps.cmdb.collection.collect_plugin.middleware import MiddlewareCollectMetrics
from apps.cmdb.collection.plugins.community.middleware.base import BaseMiddlewareCollectionPlugin


class RocketmqCollectionPlugin(BaseMiddlewareCollectionPlugin):
    supported_model_id = "rocketmq"
    metric_names = ("rocketmq_info_gauge",)
    field_mapping = {
        "inst_name": MiddlewareCollectMetrics.get_inst_name,
        "ip_addr": "ip_addr",
        "port": MiddlewareCollectMetrics.get_port,
        "version": "version",
        "install_path": "install_path",
        "configfile": partial(MiddlewareCollectMetrics.pick_value, keys=("configfile", "conf_path", "config_file")),
        "broker_id": "broker_id",
        "broker_name": "broker_name",
        "cluster_name": "cluster_name",
        "namesrv_addr": "namesrv_addr",
        "java_path": "java_path",
        "assos": MiddlewareCollectMetrics.get__host_assos,
    }
