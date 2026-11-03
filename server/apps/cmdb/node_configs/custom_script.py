# -- coding: utf-8 --
from apps.cmdb.constants.constants import CollectDriverTypes, CollectPluginTypes
from apps.cmdb.models.custom_collect_plugin import OS_WINDOWS
from apps.cmdb.node_configs.base import BaseNodeParams
from apps.cmdb.node_configs.ssh.base import SSHNodeParamsMixin
from apps.cmdb.services.custom_script_credentials import load_plugin


class CustomScriptNodeParams(SSHNodeParamsMixin, BaseNodeParams):
    """自定义脚本任务统一走哨兵键，不按目标模型注册。"""

    supported_model_id = CollectPluginTypes.CUSTOM_SCRIPT
    supported_driver_type = CollectDriverTypes.JOB
    plugin_name = "custom_script_info"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.executor_type = "job"
        self._plugin = load_plugin((self.instance.params or {}).get("custom_plugin_pk"))

    @property
    def collection_model_id(self):
        return self.model_id

    def set_credential(self, *args, **kwargs):
        if self._plugin and self._plugin.os_type == OS_WINDOWS:
            credential_data = {
                "node_id": self.instance.access_point[0]["id"],
                "username": self.credential.get("username", self.credential.get("user", "")),
                "password": "${" + self._password_env_name() + "}",
                "port": self.credential.get("port", 5986),
                "winrm_scheme": (self.instance.params or {}).get("winrm_scheme") or "https",
                "winrm_transport": (self.instance.params or {}).get("winrm_transport") or "ntlm",
                "winrm_cert_validation": bool((self.instance.params or {}).get("winrm_cert_validation", False)),
            }
        else:
            credential_data = super().set_credential(*args, **kwargs)
        plugin = self._plugin
        credential_data["custom_plugin_id"] = plugin.plugin_id if plugin else ""
        credential_data["os_type"] = plugin.os_type if plugin else ""
        credential_data["shell"] = plugin.shell if plugin else ""
        return credential_data

    def env_config(self, *args, **kwargs):
        if self._plugin and self._plugin.os_type == OS_WINDOWS:
            if not self.credential:
                return {}
            if self.has_multiple_credentials:
                return {
                    self._password_env_name(index): credential.get("password", "")
                    for index, credential in enumerate(self.credential_pool or [])
                    if isinstance(credential, dict)
                }
            return {self._password_env_name(): self.credential.get("password", "")}
        return super().env_config(*args, **kwargs)
