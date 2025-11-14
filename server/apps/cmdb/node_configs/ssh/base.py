# -- coding: utf-8 --
# @File: base.py
# @Time: 2025/11/13 14:25
# @Author: windyzhao

class SSHNodeParamsMixin:
    supported_model_id = ""
    plugin_name = f"{supported_model_id}_info"
    interval = 300  # 默认采集间隔：300秒
    host_field = "ip_addr"

    def set_credential(self, *args, **kwargs):
        host = kwargs["host"]
        node_ip = self.instance.access_point[0]["ip"]
        credential_data = {
            "node_id": self.instance.access_point[0]["id"],
            "execute_timeout": self.instance.timeout,
        }
        host_ip = host.get("ip_addr", "") if host and isinstance(host, dict) else host
        if host_ip != node_ip:
            credential_data["username"] = self.credential.get("username", "")
            credential_data["password"] = self.credential.get("password", "")
            credential_data["port"] = self.credential.get("port", 22)
        return credential_data

    def get_instance_id(self, instance):
        return f"{self.instance.id}_{instance['inst_name']}" if self.has_set_instances else f"{self.instance.id}_{instance}"
