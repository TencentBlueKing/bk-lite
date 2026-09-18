# -- coding: utf-8 --
# @File: oracle.py
# @Time: 2025/11/13 14:23
# @Author: windyzhao
from apps.cmdb.node_configs.base import BaseNodeParams
from apps.cmdb.node_configs.databases.direct_password import DirectPasswordNodeParamsMixin


class OracleNodeParams(DirectPasswordNodeParamsMixin, BaseNodeParams):
    supported_model_id = "oracle"  # 通过此属性自动注册
    plugin_name = "oracle_info"
    default_port = 1521

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.PLUGIN_MAP.update({self.model_id: self.plugin_name})
        self.host_field = "ip_addr"

    def build_extra_credential_fields(self, credential):
        payload = {}
        for key in ("service_name", "sid", "connect_type"):
            value = credential.get(key, "")
            if value:
                payload[key] = value
        return payload
