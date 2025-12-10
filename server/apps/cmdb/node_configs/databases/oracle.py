# -- coding: utf-8 --
# @File: oracle.py
# @Time: 2025/11/13 14:23
# @Author: windyzhao
from apps.cmdb.node_configs.base import BaseNodeParams


class OracleNodeParams(BaseNodeParams):
    supported_model_id = "oracle"  # 通过此属性自动注册
    plugin_name = "oracle_info"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.PLUGIN_MAP.update({self.model_id: self.plugin_name})
        self.host_field = "ip_addr"

    def set_credential(self, *args, **kwargs):
        credential_data = {
            "port": self.credential.get("port", 1521),
            "user": self.credential.get("user", ""),
            # "password": self.credential.get("password", ""),
            "password": "${PASSWORD_password}",
            "service_name": self.credential.get("service_name", ""),
        }
        return credential_data

    def get_instance_id(self, instance):
        """
        获取实例 id
        """
        if self.has_set_instances:
            return f"{self.instance.id}_{instance['inst_name']}"
        else:
            return f"{self.instance.id}_{instance}"

    @property
    def env_config(self, *args, **kwargs):
        return {"$PASSWORD_password": self.credential.get("password", "")}
