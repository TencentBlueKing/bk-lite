from apps.cmdb.node_configs.base import BaseNodeParams
from apps.cmdb.services.network_config_file_policy import validate_network_config_instance


class NetworkConfigFileNodeParams(BaseNodeParams):
    supported_model_id = "network_config_file"
    supported_driver_type = "protocol"
    plugin_name = "network_config_file_info"
    interval = 10 * 60

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.executor_type = "protocol"

    def _single_instance(self):
        instances = self.instance.instances or []
        return instances[0] if instances and isinstance(instances[0], dict) else {}

    def _target_instance(self):
        return validate_network_config_instance(self._single_instance())

    def get_hosts(self):
        hosts = ",".join(
            validate_network_config_instance(instance)["host"]
            for instance in (self.instance.instances or [])
            if isinstance(instance, dict)
        )
        return "hosts", hosts

    def _secret_env_name(self, field_name):
        return f"PASSWORD_{field_name}_{self._instance_id}"

    def _needs_enable(self):
        return bool((self.credential or {}).get("enable_password"))

    def set_credential(self, *args, **kwargs):
        params = self.instance.params or {}
        target_instance = self._target_instance()
        credential = self.credential or {}
        need_enable = self._needs_enable()
        data = {
            "username": credential.get("username", credential.get("user", "")),
            "password": "${" + self._secret_env_name("password") + "}",
            "port": credential.get("port") or target_instance.get("port") or 22,
            "config_name": params.get("config_name", ""),
            "commands": params.get("commands", ""),
            "need_enable": need_enable,
            "collect_task_id": self.instance.id,
            "target_model_id": target_instance.get("model_id"),
            "target_instance_id": target_instance.get("_id") or target_instance.get("id") or "",
            "instance_name": target_instance.get("inst_name") or target_instance.get("host") or "",
            "device_type": target_instance.get("device_type"),
            "callback_subject": "receive_config_file_result",
        }
        if need_enable:
            data["enable_password"] = "${" + self._secret_env_name("enable_password") + "}"
        if credential.get("credential_id"):
            data["credential_id"] = credential.get("credential_id")
        return data

    def env_config(self, *args, **kwargs):
        if not self.credential:
            return {}
        env = {self._secret_env_name("password"): self.credential.get("password", "")}
        if self._needs_enable():
            env[self._secret_env_name("enable_password")] = self.credential.get("enable_password", "")
        return env
