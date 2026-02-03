# -- coding: utf-8 --
# @File: network.py
# @Time: 2025/11/13 14:21
# @Author: windyzhao
from apps.cmdb.node_configs.base import BaseNodeParams


class NetworkNodeParams(BaseNodeParams):
    supported_model_id = "network"  # 通过此属性自动注册
    plugin_name = "snmp_facts"  # 插件名称
    interval = 60  # 网络设备采集间隔：300秒

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.PLUGIN_MAP.update({self.model_id: self.plugin_name})
        self.host_field = "ip_addr"

    def set_credential(self, *args, **kwargs):
        """
        生成 network 的凭据
        # 示例参数：
        # {
        #     "host": "10.10.69.246",
        #     "version": "v3",
        #     "username": "weops",
        #     "level": "authPriv",
        #     "integrity": "sha",
        #     "privacy": "aes",
        #     "authkey": "WeOps@2024",
        #     "privkey": "1145141919",
        #     "timeout": 5,
        #     "retries": 3,
        #     "snmp_port": 161,
        #     "community": "",
        # }
        """
        _community = "PASSWORD_community_{instance_id}".format(instance_id=self._instance_id)
        _authkey = "PASSWORD_authkey_{instance_id}".format(instance_id=self._instance_id)
        _privkey = "PASSWORD_privkey_{instance_id}".format(instance_id=self._instance_id)
        credential_data = {
            "snmp_port": self.credential.get("snmp_port", 161),
            "community": "${" + _community + "}",  # 团体字 仅v1/v2c使用
            "version": self.credential.get("version", ""),
            "username": self.credential.get("username", ""),
            "level": self.credential.get("level", ""),
            "integrity": self.credential.get("integrity", ""),  # 哈希算法
            "privacy": self.credential.get("privacy", ""),  # 加密算法
            "authkey": "${" + _authkey + "}",
            "privkey": "${" + _privkey + "}",
            "has_network_topo": self.has_network_topo
        }
        return credential_data

    def env_config(self, *args, **kwargs):
        env_config = {
            f"PASSWORD_authkey_{self._instance_id}": self.credential.get("authkey", ""),
            f"PASSWORD_privkey_{self._instance_id}": self.credential.get("privkey", ""),
            f"PASSWORD_community_{self._instance_id}": self.credential.get("community", ""),
        }
        return env_config
