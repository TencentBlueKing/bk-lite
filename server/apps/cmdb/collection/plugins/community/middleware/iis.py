from functools import partial

from apps.cmdb.collection.collect_plugin.middleware import MiddlewareCollectMetrics
from apps.cmdb.collection.plugins.community.middleware.base import BaseMiddlewareCollectionPlugin


class IisCollectionPlugin(BaseMiddlewareCollectionPlugin):
    supported_model_id = "iis"
    metric_names = ("iis_info_gauge",)
    field_mapping = {
        "inst_name": MiddlewareCollectMetrics.get_inst_name,
        "ip_addr": "ip_addr",
        "port": MiddlewareCollectMetrics.get_port,
        "version": "version",
        "webapp": "webapp",
        "virdir": "virdir",
        "configfile": partial(MiddlewareCollectMetrics.pick_value, keys=("configfile", "config_path")),
        "apppool": "apppool",
        "website": partial(MiddlewareCollectMetrics.pick_value, keys=("website", "server_name")),
        "apppool_count": "apppool_count",
        "webapp_count": "webapp_count",
        "phys_path": "phys_path",
        "server_name": "server_name",
        "max_concur_connect": "max_concur_connect",
        "assos": MiddlewareCollectMetrics.get__host_assos,
    }
