# -- coding: utf-8 --
# @File: mssql.py
# @Time: 2026/04/14 23:49
# @Author: Sisyphus

from apps.cmdb.node_configs.base import BaseNodeParams
from apps.cmdb.node_configs.databases.direct_password import DirectPasswordNodeParamsMixin


class MssqlNodeParams(DirectPasswordNodeParamsMixin, BaseNodeParams):
    supported_model_id = "mssql"
    plugin_name = "mssql_info"
    default_port = 1433

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.PLUGIN_MAP.update({self.model_id: self.plugin_name})
        self.host_field = "ip_addr"
        self.executor_type = "protocol"

    def build_extra_credential_fields(self, credential):
        return {"database": credential.get("database", "master")}
