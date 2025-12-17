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
        if not self.credential:
            return {}
        host = kwargs["host"]
        node_ip = self.instance.access_point[0]["ip"]
        credential_data = {
            "node_id": self.instance.access_point[0]["id"],
            "execute_timeout": self.instance.timeout,
        }
        host_ip = host.get("ip_addr", "") if host and isinstance(host, dict) else host
        if host_ip != node_ip:
            _password = "PASSWORD_password_{end_start}".format(end_start=self.get_instance_id(host))
            credential_data["password"] = "${" + _password + "}"
            credential_data["username"] = self.credential.get("username", self.credential.get("user", ""))
            credential_data["port"] = self.credential.get("port", 22)
        return credential_data

    def get_instance_id(self, instance):
        if self.has_set_instances:
            return f"{self.instance.id}_{instance['_id']}"
        return f"{self.instance.id}_{instance}".replace(".", "")

    def env_config(self, *args, **kwargs):
        if not self.credential:
            return {}
        host = kwargs["host"]
        node_ip = self.instance.access_point[0]["ip"]
        host_ip = host.get("ip_addr", "") if host and isinstance(host, dict) else host
        if host_ip != node_ip:
            _password = "PASSWORD_password_{end_start}".format(end_start=self.get_instance_id(host))
            return {_password: self.credential.get("password", "")}
        return {}
