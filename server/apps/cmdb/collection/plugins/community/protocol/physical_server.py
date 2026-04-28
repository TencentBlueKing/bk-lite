from apps.cmdb.collection.collect_plugin.protocol import ProtocolCollectMetrics
from apps.cmdb.collection.plugins.community.protocol.base import BaseProtocolCollectionPlugin


class PhysicalServerIPMICollectionPlugin(BaseProtocolCollectionPlugin):
    supported_model_id = "physcial_server"
    metric_names = ("physcial_server_info_gauge",)
    field_mapping = {
        "ip_addr": "ip_addr",
        "serial_number": "serial_number",
        "model": "model",
        "brand": "brand",
        "asset_code": "asset_code",
        "board_vendor": "board_vendor",
        "board_model": "board_model",
        "board_serial": "board_serial",
        "inst_name": lambda self, data: self.get_inst_name(data),
    }

    def get_inst_name(self, data):
        # IPMI 路径只拿带外基础身份信息，实例识别优先级遵循变更约定：
        # serial_number > ip_addr > model，避免直接复用 protocol 默认实例名规则。
        serial_number = data.get("serial_number")
        if serial_number:
            return serial_number
        ip_addr = data.get("ip_addr")
        if ip_addr:
            return ip_addr
        model = data.get("model")
        if model and ip_addr:
            return f"{model}-{ip_addr}"
        return model or "physcial_server"

    @property
    def model_field_mapping(self):
        return {self.model_id: self.field_mapping}

    def format_data(self, data):
        if not isinstance(data, dict):
            return
        for index_data in data.get("result", []):
            metric_name = index_data["metric"].get("__name__")
            if metric_name not in self.metric_names:
                continue
            if index_data["metric"].get("collect_status", "failed") == "failed":
                continue
            self.collection_metrics_dict[metric_name].append(index_data["metric"])

    def format_metrics(self):
        result = []
        mapping = self.model_field_mapping.get(self.model_id, {})
        for metric_key in self.metric_names:
            for index_data in self.collection_metrics_dict.get(metric_key, []):
                data = {}
                for field, key_or_func in mapping.items():
                    if callable(key_or_func):
                        value = key_or_func(index_data)
                    else:
                        value = index_data.get(key_or_func)
                    # 这里显式跳过空值，避免 IPMI 的缺失字段把现有 SSH 链路写入的非空资产信息覆盖掉。
                    if value in (None, ""):
                        continue
                    data[field] = value
                if data:
                    result.append(data)
        self.result[self.model_id] = result
