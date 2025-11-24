# -- coding: utf-8 --
# @File: vmware.py
# @Time: 2025/11/13 14:20
# @Author: windyzhao
from apps.cmdb.node_configs.base import BaseNodeParams


class VmwareNodeParams(BaseNodeParams):
    supported_model_id = "vmware_vc"  # 通过此属性自动注册
    plugin_name = "vmware_info"
    interval = 60  # VMware采集间隔：60秒

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 当 instance.model_id 为 "network" 时，PLUGIN_MAP 配置为 "snmp_facts"
        self.PLUGIN_MAP.update({self.model_id: self.plugin_name})
        self.host_field = "ip_addr"

    def get_host_ip_addr(self, host):
        if isinstance(host, dict):
            ip_addr = host.get(self.host_field, "")
        else:
            ip_addr = host
        return "hostname", ip_addr

    def set_credential(self, *args, **kwargs):
        """
        生成 vmware vc 的凭据
        """
        credential_data = {
            "username": self.credential.get("username"),
            "password": self.credential.get("password"),
            "port": self.credential.get("port", 443),
            "ssl": str(self.credential.get("ssl", False)).lower(),
        }
        return credential_data

    def get_instance_id(self, instance):
        """
        获取实例 id
        """
        return f"{self.instance.id}_{instance['inst_name']}"
