# -- coding: utf-8 --
# @File: postgresql.py
# @Time: 2026/01/19 20:12
# @Author: Sisyphus

from apps.cmdb.node_configs.base import BaseNodeParams
from apps.cmdb.node_configs.databases.direct_password import DirectPasswordNodeParamsMixin


class PostgresqlNodeParams(DirectPasswordNodeParamsMixin, BaseNodeParams):
    supported_model_id = "postgresql"
    plugin_name = "postgresql_info"
    default_port = 5432

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.PLUGIN_MAP.update({self.model_id: self.plugin_name})
        self.host_field = "ip_addr"
        self.executor_type = "protocol"
