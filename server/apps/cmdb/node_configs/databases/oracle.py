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
        _instance_id = self.get_instance_id(instance=kwargs["host"])
        _password = f"PASSWORD_password_{_instance_id}"
        credential_data = {
            "port": self.credential.get("port", 1521),
            "user": self.credential.get("user", ""),
            # "password": self.credential.get("password", ""),
            "password": "${" + _password + "}",
            "service_name": self.credential.get("service_name", ""),
        }
        return credential_data

    def get_instance_id(self, instance):
        """
        获取实例 id
        """
        if self.has_set_instances:
            return f"{self.instance.id}_{instance['_id']}"
        else:
            return f"{self.instance.id}_{instance}".replace(".", "")

    def env_config(self, *args, **kwargs):
        host = kwargs["host"]
        _instance_id = self.get_instance_id(instance=host)
        return {f"PASSWORD_password_{_instance_id}": self.credential.get("password", "")}
