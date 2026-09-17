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
            # 脚本执行上限由 agent 侧硬编码（默认 60s）；表单 timeout 仅作单对象采集预算。
        }
        if self.credential:
            credential_data.update(self._auth_payload(self.credential))
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
                env.update(self._auth_env(credential, index))
        else:
            env.update(self._auth_env(self.credential))
        return env

    def build_credentials_pool(self):
        if not self.has_multiple_credentials:
            return []
        pool = []
        for index, credential in enumerate(self.credential_pool or []):
            item = {
                "node_id": self.instance.access_point[0]["id"],
                "port": credential.get("port", 22),
                "username": credential.get("username", credential.get("user", "")),
            }
            item.update(self._auth_payload(credential, index))
            if credential.get("credential_id"):
                item["credential_id"] = credential.get("credential_id")
            pool.append(item)
        return pool

    def _auth_payload(self, credential, index=None):
        if credential.get("private_key"):
            payload = {"private_key": "${" + self._private_key_env_name(index) + "}"}
            if credential.get("passphrase"):
                payload["passphrase"] = "${" + self._passphrase_env_name(index) + "}"
            return payload
        return {"password": "${" + self._password_env_name(index) + "}"}

    def _auth_env(self, credential, index=None):
        if credential.get("private_key"):
            env = {self._private_key_env_name(index): credential["private_key"]}
            if credential.get("passphrase"):
                env[self._passphrase_env_name(index)] = credential["passphrase"]
            return env
        return {self._password_env_name(index): credential.get("password", "")}

    def _password_env_name(self, index=None):
        if index is None:
            return "PASSWORD_password_{end_start}".format(end_start=self._instance_id)
        return "PASSWORD_password_{end_start}_{index}".format(end_start=self._instance_id, index=index)

    def _private_key_env_name(self, index=None):
        suffix = "" if index is None else f"_{index}"
        return f"PRIVATEKEY_private_key_{self._instance_id}{suffix}"

    def _passphrase_env_name(self, index=None):
        suffix = "" if index is None else f"_{index}"
        return f"PASSPHRASE_passphrase_{self._instance_id}{suffix}"
