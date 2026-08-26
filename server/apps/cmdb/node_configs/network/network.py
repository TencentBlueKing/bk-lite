# -- coding: utf-8 --
# @File: network.py
# @Time: 2025/11/13 14:21
# @Author: windyzhao
from apps.cmdb.models.collect_model import (
    COLLECTION_ROLE_DEVICE,
    COLLECTION_ROLE_TOPOLOGY,
    DEFAULT_TOPOLOGY_TIMEOUT_SECONDS,
    normalize_topology_contract,
)
from apps.cmdb.node_configs.base import BaseNodeParams


class NetworkNodeParams(BaseNodeParams):
    """设备通道：仅设备和接口，不携带拓扑参数。"""

    supported_model_id = "network"
    plugin_name = "snmp_facts"
    interval = 60

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.PLUGIN_MAP.update({self.model_id: self.plugin_name})
        self.host_field = "ip_addr"
        self.topology_contract = normalize_topology_contract(getattr(self.instance, "params", {}))
        self.has_network_topo = self.topology_contract["has_network_topo"]
        self.collection_role = COLLECTION_ROLE_DEVICE
        self.channel_config_version = int(self.topology_contract.get("device_channel_config_version") or 1)

    def set_credential(self, *args, **kwargs):
        _community = self._secret_env_name("community")
        _authkey = self._secret_env_name("authkey")
        _privkey = self._secret_env_name("privkey")
        credential_data = {
            "snmp_port": self.credential.get("snmp_port", 161),
            "community": "${" + _community + "}",
            "version": self.credential.get("version", ""),
            "username": self.credential.get("username", ""),
            "level": self.credential.get("level", ""),
            "integrity": self.credential.get("integrity", ""),
            "privacy": self.credential.get("privacy", ""),
            "authkey": "${" + _authkey + "}",
            "privkey": "${" + _privkey + "}",
            # 设备通道显式关闭内联拓扑；残留字段由 agent 忽略。
            "has_network_topo": False,
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
                "has_network_topo": False,
            }
            if credential.get("credential_id"):
                item["credential_id"] = credential.get("credential_id")
            pool.append(item)
        return pool

    def _secret_env_name(self, field_name, index=None):
        # 凭据环境变量按任务级 metric_scope 命名，双通道共享同一份明文引用。
        scope = self.metric_scope_id
        if index is None:
            return f"PASSWORD_{field_name}_{scope}"
        return f"PASSWORD_{field_name}_{scope}_{index}"


class NetworkTopoNodeParams(NetworkNodeParams):
    """拓扑通道：独立节点配置 ID，共享 metric_scope_id 与凭据。"""

    supported_model_id = "network_topo"
    plugin_name = "snmp_topo"
    interval = 300

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.collection_role = COLLECTION_ROLE_TOPOLOGY
        self.channel_config_version = int(self.topology_contract.get("topology_channel_config_version") or 1)
        self.model_id = "network_topo"
        self.timeout = int(self.topology_contract.get("topology_timeout") or DEFAULT_TOPOLOGY_TIMEOUT_SECONDS)

    @property
    def config_id(self):
        return f"{self.metric_scope_id}_topology"

    @property
    def resolved_interval(self) -> int:
        minutes = int(self.topology_contract.get("topology_interval_minutes") or 0)
        if minutes >= 1:
            return max(self.MIN_INTERVAL_SECONDS, minutes * 60)
        return super().resolved_interval

    def set_credential(self, *args, **kwargs):
        credential_data = super().set_credential(*args, **kwargs)
        credential_data.update(
            {
                "has_network_topo": True,
                "topology_protocols": ",".join(self.topology_contract["topology_protocols"]),
                "topology_fallback_strategy": self.topology_contract["topology_fallback_strategy"],
                "min_confidence": self.topology_contract["min_confidence"],
            }
        )
        return credential_data

    def build_credentials_pool(self):
        pool = super().build_credentials_pool()
        for item in pool:
            item["has_network_topo"] = True
            item["topology_protocols"] = ",".join(self.topology_contract["topology_protocols"])
            item["topology_fallback_strategy"] = self.topology_contract["topology_fallback_strategy"]
            item["min_confidence"] = self.topology_contract["min_confidence"]
        return pool
