from apps.cmdb.collection.collect_plugin.protocol import ProtocolCollectMetrics
from apps.cmdb.collection.plugins.community.protocol.base import BaseProtocolCollectionPlugin


class SslCerCollectionPlugin(BaseProtocolCollectionPlugin):
    supported_model_id = "ssl_cer"
    metric_names = ("ssl_cer_info_gauge",)
    field_mapping = {
        "inst_name": "inst_name",
        "issuer": "issuer",
        "create_time": (ProtocolCollectMetrics.convert_datetime_format, "create_time"),
        "expired_time": (ProtocolCollectMetrics.convert_datetime_format, "expired_time"),
    }

    def get_inst_name(self, data):
        return str(data.get("inst_name") or "").strip()
