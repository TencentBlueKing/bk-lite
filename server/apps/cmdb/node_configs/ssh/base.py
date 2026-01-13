# -- coding: utf-8 --
# @File: base.py
# @Time: 2025/11/13 14:25
# @Author: windyzhao

class SSHNodeParamsMixin:
    supported_model_id = ""
    plugin_name = f"{supported_model_id}_info"
    interval = 300  # 默认采集间隔：300秒
    host_field = "ip_addr"
    executor_type = "job"  # 默认执行器类型

    def set_credential(self, *args, **kwargs):
        credential_data = {
            "node_id": self.instance.access_point[0]["id"],
            "execute_timeout": self.instance.timeout,
        }
        if self.credential:
            _password = "PASSWORD_password_{end_start}".format(end_start=self._instance_id)
            credential_data["password"] = "${" + _password + "}"
            credential_data["port"] = self.credential.get("port", 22)
            credential_data["username"] = self.credential.get("username", self.credential.get("user", ""))
        return credential_data

    @property
    def tags(self):
        tags = super().tags
        tags["collect_type"] = "ssh"
        return tags

    def env_config(self, *args, **kwargs):
        if not self.credential:
            return {}
        _password = "PASSWORD_password_{end_start}".format(end_start=self._instance_id)
        return {_password: self.credential.get("password", "")}
