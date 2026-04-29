from functools import partial

from apps.cmdb.collection.collect_plugin.middleware import MiddlewareCollectMetrics
from apps.cmdb.collection.plugins.community.middleware.base import BaseMiddlewareCollectionPlugin


class WebsphereCollectionPlugin(BaseMiddlewareCollectionPlugin):
    supported_model_id = "websphere"
    metric_names = ("websphere_info_gauge",)
    field_mapping = {
        "inst_name": MiddlewareCollectMetrics.get_inst_name,
        "ip_addr": "ip_addr",
        "port": MiddlewareCollectMetrics.get_port,
        "version": "version",
        "bin_path": "bin_path",
        "java_path": "java_path",
        "java_version": "java_version",
        "server_name": partial(MiddlewareCollectMetrics.pick_value, keys=("server_name", "ser_name")),
        "cell": partial(MiddlewareCollectMetrics.pick_value, keys=("cell", "cell_name")),
        "node": partial(MiddlewareCollectMetrics.pick_value, keys=("node", "node_name")),
        "initial_heap_size": partial(MiddlewareCollectMetrics.pick_value, keys=("initial_heap_size", "jvm_xms")),
        "maximum_heap_size": partial(MiddlewareCollectMetrics.pick_value, keys=("maximum_heap_size", "jvm_xmx")),
        "threadpool": "threadpool",
        "jdbc": "jdbc",
        "port_list": partial(MiddlewareCollectMetrics.pick_value, keys=("port_list", "soap_port")),
        "assos": MiddlewareCollectMetrics.get__host_assos,
    }
