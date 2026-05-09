from apps.cmdb.collection.collect_plugin.middleware import MiddlewareCollectMetrics
from apps.cmdb.collection.plugins.community.middleware.base import BaseMiddlewareCollectionPlugin


class JettyCollectionPlugin(BaseMiddlewareCollectionPlugin):
    supported_model_id = "jetty"
    metric_names = ("jetty_info_gauge",)
    field_mapping = {
        "inst_name": MiddlewareCollectMetrics.get_inst_name,
        "ip_addr": "ip_addr",
        "port": MiddlewareCollectMetrics.get_port,
        "version": "version",
        "jetty_home": "jetty_home",
        "bin_path": "bin_path",
        "monitored_dir": "monitored_dir",
        "java_path": "java_path",
        "java_version": "java_version",
        "conf_path": "conf_path",
        "java_vendor": "java_vendor",
        "assos": MiddlewareCollectMetrics.get__host_assos,
    }
