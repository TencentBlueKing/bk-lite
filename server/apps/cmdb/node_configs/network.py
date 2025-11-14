# -- coding: utf-8 --
# @File: network.py
# @Time: 2025/11/13 14:21
# @Author: windyzhao
from apps.cmdb.node_configs.base import BaseNodeParams


class NetworkNodeParams(BaseNodeParams):
    supported_model_id = "network"  # 通过此属性自动注册
    plugin_name = "snmp_facts"  # 插件名称
    interval = 300  # 网络设备采集间隔：300秒

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 当 instance.model_id 为 "vmware_vc" 时，PLUGIN_MAP 配置为 "vmware_info"
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

        credential_data = {
            "snmp_port": self.credential.get("snmp_port", 161),
            "community": self.credential.get("community", ""),
            "version": self.credential.get("version", ""),
            "username": self.credential.get("username", ""),
            "level": self.credential.get("level", ""),
            "integrity": self.credential.get("integrity", ""),
            "privacy": self.credential.get("privacy", ""),
            "authkey": self.credential.get("authkey", ""),
            "privkey": self.credential.get("privkey", ""),
            "timeout": self.credential.get("timeout", "1"),
        }
        if self.model_id == "network_topo":
            credential_data.update({"topo": "true"})
        return credential_data

    def get_instance_id(self, instance):
        """
        获取实例 id
        """
        if self.has_set_instances:
            return f"{self.instance.id}_{instance['inst_name']}"
        else:
            return f"{self.instance.id}_{instance}"
