from apps.cmdb.collection.collect_plugin.protocol import ProtocolCollectMetrics
from apps.cmdb.collection.plugins.community.protocol.base import BaseProtocolCollectionPlugin


class InfluxdbCollectionPlugin(BaseProtocolCollectionPlugin):
    """InfluxDB 采集（协议采集，对齐 MySQL）。兼容 1.x/2.x，优先 2.x。"""

    supported_model_id = "influxdb"
    metric_names = ("influxdb_info_gauge",)
    field_mapping = {
        "inst_name": ProtocolCollectMetrics.get_inst_name,
        "ip_addr": "ip_addr",
        "port": "port",
        "version": "version",
        "data_dir": "data_dir",
        "wal_dir": "wal_dir",
        "meta_dir": "meta_dir",
        "engine": "engine",
        "http_bind_address": "http_bind_address",
        "auth_enabled": "auth_enabled",
        "https_enabled": "https_enabled",
        "max_concurrent_queries": "max_concurrent_queries",
    }
