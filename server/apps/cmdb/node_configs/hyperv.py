# -- coding: utf-8 --
"""Hyper-V 配置采集的 NodeParams。

任务通过接入点 WinRM 执行 hyperv_discover.ps1。连接方式来自任务 params，
账号和端口来自凭据。密码只以 ${ENV} 占位符进入 headers，真实值经 env_config 注入。
"""

from apps.cmdb.constants.constants import CollectDriverTypes
from apps.cmdb.node_configs.base import BaseNodeParams


class HypervNodeParams(BaseNodeParams):
    supported_model_id = "hyperv_host"
    supported_driver_type = CollectDriverTypes.JOB
    plugin_name = "hyperv_info"
    host_field = "ip_addr"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.executor_type = "job"

    def set_credential(self, *args, **kwargs):
        return self._build_credential(self.credential)

    def build_credentials_pool(self):
        if not self.has_multiple_credentials:
            return []
        return [
            self._build_credential(credential, index) for index, credential in enumerate(self.credential_pool or []) if isinstance(credential, dict)
        ]

    def env_config(self, *args, **kwargs):
        if not self.credential:
            return {}
        env = {}
        if self.has_multiple_credentials:
            items = [(index, credential) for index, credential in enumerate(self.credential_pool or [])]
        else:
            items = [(None, self.credential)]
        for index, credential in items:
            if not isinstance(credential, dict):
                continue
            secret = credential.get("password")
            if secret:
                env[self._secret_env_name(index)] = secret
        return env

    def _build_credential(self, credential, index=None):
        if not isinstance(credential, dict) or not credential:
            return {}
        params = self.instance.params or {}
        payload = {
            "node_id": self.instance.access_point[0]["id"],
            "username": credential.get("username", ""),
            "port": credential.get("port") or 5985,
            "winrm_scheme": params.get("winrm_scheme") or "http",
            "winrm_transport": params.get("winrm_transport") or "ntlm",
            "winrm_cert_validation": params.get("winrm_cert_validation", False),
        }
        if credential.get("password"):
            payload["password"] = "${" + self._secret_env_name(index) + "}"
        if credential.get("credential_id"):
            payload["credential_id"] = credential["credential_id"]
        return payload

    def _secret_env_name(self, index=None):
        base = f"PASSWORD_password_{self._instance_id}"
        if index is None:
            return base
        return f"{base}_{index}"
