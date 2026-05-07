from apps.cmdb.collection.collect_plugin.middleware import MiddlewareCollectMetrics
from apps.cmdb.collection.plugins.community.middleware.base import BaseMiddlewareCollectionPlugin


class HaproxyCollectionPlugin(BaseMiddlewareCollectionPlugin):
    supported_model_id = "haproxy"
    metric_names = ("haproxy_info_gauge",)
    field_mapping = {
        "inst_name": MiddlewareCollectMetrics.get_inst_name,
        "ip_addr": "ip_addr",
        "port": MiddlewareCollectMetrics.get_port,
        "version": "version",
        "install_path": "install_path",
        "conf_file": "conf_file",
        "defaults_maxconn": "defaults_maxconn",
        "defaults_mode": "defaults_mode",
        "defaults_retries": "defaults_retries",
        "global_group_name": "global_group_name",
        "global_maxconn": "global_maxconn",
        "global_pidfile": "global_pidfile",
        "global_user_name": "global_user_name",
        "assos": MiddlewareCollectMetrics.get__host_assos,
    }
