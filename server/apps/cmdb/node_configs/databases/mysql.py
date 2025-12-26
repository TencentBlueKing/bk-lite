# -- coding: utf-8 --
# @File: mysql.py
# @Time: 2025/11/13 14:23
# @Author: windyzhao
from apps.cmdb.node_configs.base import BaseNodeParams


class MysqlNodeParams(BaseNodeParams):
    supported_model_id = "mysql"  # 通过此属性自动注册
    plugin_name = "mysql_info"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.PLUGIN_MAP.update({self.model_id: self.plugin_name})
        self.host_field = "ip_addr"

    def set_credential(self, *args, **kwargs):
        _password = f"PASSWORD_password_{self._instance_id}"
        credential_data = {
            "port": self.credential.get("port", 3306),
            "user": self.credential.get("user", ""),
            "password": "${" + _password + "}",
        }
        return credential_data

    def env_config(self, *args, **kwargs):
        return {f"PASSWORD_password_{self._instance_id}": self.credential.get("password", "")}
