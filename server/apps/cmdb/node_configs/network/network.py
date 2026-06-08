# -- coding: utf-8 --
# @File: network.py
# @Time: 2025/11/13 14:21
# @Author: windyzhao
from apps.cmdb.node_configs.base import BaseNodeParams
from apps.cmdb.models.collect_model import normalize_topology_contract


class NetworkNodeParams(BaseNodeParams):
    supported_model_id = "network"  # 通过此属性自动注册
    plugin_name = "snmp_facts"  # 插件名称
    interval = 60  # 网络设备采集间隔：300秒

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.PLUGIN_MAP.update({self.model_id: self.plugin_name})
        self.host_field = "ip_addr"
        self.topology_contract = normalize_topology_contract(getattr(self.instance, "params", {}))
        self.has_network_topo = self.topology_contract["has_network_topo"]

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
        _community = self._secret_env_name("community")
        _authkey = self._secret_env_name("authkey")
        _privkey = self._secret_env_name("privkey")
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
            "has_network_topo": self.has_network_topo,
            "topology_protocols": list(self.topology_contract["topology_protocols"]),
            "topology_fallback_strategy": self.topology_contract["topology_fallback_strategy"],
            "min_confidence": self.topology_contract["min_confidence"],
        }
        if self.credential.get("credential_id"):
            credential_data["credential_id"] = self.credential.get("credential_id")
        return credential_data

    def env_config(self, *args, **kwargs):
        env_config = {}
        if self.has_multiple_credentials:
            for index, credential in enumerate(self.credential_pool or []):
                env_config[self._secret_env_name("authkey", index)] = credential.get("authkey", "")
                env_config[self._secret_env_name("privkey", index)] = credential.get("privkey", "")
                env_config[self._secret_env_name("community", index)] = credential.get("community", "")
        else:
            env_config = {
                self._secret_env_name("authkey"): self.credential.get("authkey", ""),
                self._secret_env_name("privkey"): self.credential.get("privkey", ""),
                self._secret_env_name("community"): self.credential.get("community", ""),
            }
        return env_config

    def build_credentials_pool(self):
        if not self.has_multiple_credentials:
            return []
        pool = []
        for index, credential in enumerate(self.credential_pool or []):
            item = {
                "snmp_port": credential.get("snmp_port", 161),
                "community": "${" + self._secret_env_name("community", index) + "}",
                "version": credential.get("version", ""),
                "username": credential.get("username", ""),
                "level": credential.get("level", ""),
                "integrity": credential.get("integrity", ""),
                "privacy": credential.get("privacy", ""),
                "authkey": "${" + self._secret_env_name("authkey", index) + "}",
                "privkey": "${" + self._secret_env_name("privkey", index) + "}",
                "has_network_topo": self.has_network_topo,
                "topology_protocols": list(self.topology_contract["topology_protocols"]),
                "topology_fallback_strategy": self.topology_contract["topology_fallback_strategy"],
                "min_confidence": self.topology_contract["min_confidence"],
            }
            if credential.get("credential_id"):
                item["credential_id"] = credential.get("credential_id")
            pool.append(item)
        return pool

    def _secret_env_name(self, field_name, index=None):
        if index is None:
            return f"PASSWORD_{field_name}_{self._instance_id}"
        return f"PASSWORD_{field_name}_{self._instance_id}_{index}"
