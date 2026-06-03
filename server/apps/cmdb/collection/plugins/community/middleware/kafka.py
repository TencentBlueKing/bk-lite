from apps.cmdb.collection.collect_plugin.middleware import MiddlewareCollectMetrics
from apps.cmdb.collection.plugins.community.middleware.base import BaseMiddlewareCollectionPlugin


class KafkaCollectionPlugin(BaseMiddlewareCollectionPlugin):
    supported_model_id = "kafka"
    metric_names = ("kafka_info_gauge",)
    field_mapping = {
        "inst_name": MiddlewareCollectMetrics.get_inst_name,
        "ip_addr": "ip_addr",
        "port": "port",
        "version": "version",
        "install_path": "install_path",
        "conf_path": "conf_path",
        "log_path": "log_path",
        "java_path": "java_path",
        "java_version": "java_version",
        "xms": "xms",
        "xmx": "xmx",
        "broker_id": "broker_id",
        "io_threads": "io_threads",
        "network_threads": "network_threads",
        "socket_receive_buffer_bytes": "socket_receive_buffer_bytes",
        "socket_request_max_bytes": "socket_request_max_bytes",
        "socket_send_buffer_bytes": "socket_send_buffer_bytes",
    }
