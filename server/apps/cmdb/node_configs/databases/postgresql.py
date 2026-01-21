# -- coding: utf-8 --
# @File: postgresql.py
# @Time: 2026/01/19 20:12
# @Author: Sisyphus

from apps.cmdb.node_configs.base import BaseNodeParams


class PostgresqlNodeParams(BaseNodeParams):
    supported_model_id = "postgresql"
    plugin_name = "postgresql_info"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.PLUGIN_MAP.update({self.model_id: self.plugin_name})
        self.host_field = "ip_addr"
        self.executor_type = "protocol"

    def set_credential(self, *args, **kwargs):
        _password = f"PASSWORD_password_{self._instance_id}"
        return {
            "port": self.credential.get("port", 5432),
            "user": self.credential.get("user", ""),
            "password": "${" + _password + "}",
        }

    def env_config(self, *args, **kwargs):
        return {f"PASSWORD_password_{self._instance_id}": self.credential.get("password", "")}
