from apps.cmdb.collection.collect_plugin.middleware import MiddlewareCollectMetrics
from apps.cmdb.collection.plugins.community.middleware.base import BaseMiddlewareCollectionPlugin


class SparkCollectionPlugin(BaseMiddlewareCollectionPlugin):
    supported_model_id = "spark"
    metric_names = ("spark_info_gauge",)
    field_mapping = {
        "inst_name": MiddlewareCollectMetrics.get_inst_name,
        "ip_addr": "ip_addr",
        "port": MiddlewareCollectMetrics.get_port,
        "version": "version",
        "install_path": "install_path",
        "webui_port": "webui_port",
        "java_path": "java_path",
        "java_version": "java_version",
        "log_path": "log_path",
    }
