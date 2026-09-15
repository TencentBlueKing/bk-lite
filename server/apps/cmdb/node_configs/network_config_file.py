from apps.cmdb.node_configs.base import BaseNodeParams
from apps.cmdb.node_configs.config_artifact import ConfigArtifactNodeParamsMixin
from apps.cmdb.services.network_config_file_policy import encode_http_header_commands, normalize_network_config_instance

TELNET_ALIASES = {"telnet", "asynctelnet"}
SSH_DEFAULT_PORT = 22
TELNET_DEFAULT_PORT = 23


def resolve_transport_protocol(credential=None):
    source = credential if isinstance(credential, dict) else {}
    for key in ("transport_protocol", "protocol"):
        raw = str(source.get(key) or "").strip().lower()
        if raw in TELNET_ALIASES:
            return "telnet"
        if raw in {"ssh", "asyncssh"}:
            return "ssh"
    return "ssh"


def default_port_for_transport(transport_protocol):
    return TELNET_DEFAULT_PORT if transport_protocol == "telnet" else SSH_DEFAULT_PORT


class NetworkConfigFileNodeParams(ConfigArtifactNodeParamsMixin, BaseNodeParams):
    supported_model_id = "network_config_file"
    supported_driver_type = "protocol"
    plugin_name = "network_config_file_info"
    interval = 10 * 60

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.executor_type = "protocol"

    def _target_instance(self):
        # P2-2.1: 改用 normalize(只规范化,不再二次校验;serializer 已校验)
        return normalize_network_config_instance(self._current_target_instance())

    def get_hosts(self):
        target = self._current_target_instance()
        return "hosts", (target.get("ip_addr") or target.get("host") or "").strip()

    def _secret_env_name(self, field_name):
        return f"PASSWORD_{field_name}_{self._instance_id}"

    def _needs_enable(self):
        return bool((self.credential or {}).get("enable_password"))

    def set_credential(self, *args, **kwargs):
        params = self.instance.params or {}
        target_instance = self._target_instance()
        credential = self.credential or {}
        need_enable = self._needs_enable()
        transport_protocol = resolve_transport_protocol(credential)
        data = {
            "username": credential.get("username", credential.get("user", "")),
            "password": "${" + self._secret_env_name("password") + "}",
            "transport_protocol": transport_protocol,
            "port": credential.get("port") or target_instance.get("port") or default_port_for_transport(transport_protocol),
            "config_name": params.get("config_name", ""),
            "commands": encode_http_header_commands(params.get("commands", "")),
            "need_enable": need_enable,
            "collect_task_id": self.instance.id,
            "target_model_id": target_instance.get("model_id"),
            "target_instance_uuid": target_instance.get("inst_uuid") or "",
            "instance_name": target_instance.get("inst_name") or target_instance.get("host") or "",
            "device_type": target_instance.get("device_type"),
            "callback_subject": "receive_config_file_result",
            "protocol_version": "2",
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
