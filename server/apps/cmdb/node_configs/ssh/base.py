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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.executor_type = "job"

    def set_credential(self, *args, **kwargs):
        credential_data = {
            "node_id": self.instance.access_point[0]["id"],
            "execute_timeout": self.instance.timeout,
        }
        if self.credential:
            _password = self._password_env_name()
            credential_data["password"] = "${" + _password + "}"
            credential_data["port"] = self.credential.get("port", 22)
            credential_data["username"] = self.credential.get("username", self.credential.get("user", ""))
            if self.credential.get("credential_id"):
                credential_data["credential_id"] = self.credential.get("credential_id")
        return credential_data

    def env_config(self, *args, **kwargs):
        if not self.credential:
            return {}
        env = {}
        if self.has_multiple_credentials:
            for index, credential in enumerate(self.credential_pool or []):
                env[self._password_env_name(index)] = credential.get("password", "")
        else:
            env[self._password_env_name()] = self.credential.get("password", "")
        return env

    def build_credentials_pool(self):
        if not self.has_multiple_credentials:
            return []
        pool = []
        for index, credential in enumerate(self.credential_pool or []):
            item = {
                "node_id": self.instance.access_point[0]["id"],
                "execute_timeout": self.instance.timeout,
                "password": "${" + self._password_env_name(index) + "}",
                "port": credential.get("port", 22),
                "username": credential.get("username", credential.get("user", "")),
            }
            if credential.get("credential_id"):
                item["credential_id"] = credential.get("credential_id")
            pool.append(item)
        return pool

    def _password_env_name(self, index=None):
        if index is None:
            return "PASSWORD_password_{end_start}".format(end_start=self._instance_id)
        return "PASSWORD_password_{end_start}_{index}".format(end_start=self._instance_id, index=index)
