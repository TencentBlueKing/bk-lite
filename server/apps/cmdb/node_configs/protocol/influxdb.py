from apps.cmdb.constants.constants import CollectDriverTypes
from apps.cmdb.node_configs.base import BaseNodeParams


def _as_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


class InfluxdbNodeParams(BaseNodeParams):
    supported_model_id = "influxdb"
    supported_driver_type = CollectDriverTypes.PROTOCOL
    plugin_name = "influxdb_info"
    host_field = "ip_addr"

    def set_credential(self, *args, **kwargs):
        credential_data = {
            "port": self.credential.get("port", 8086),
            "ssl": str(self.credential.get("scheme", "http")).lower() == "https",
            "verify_tls": _as_bool(
                self.credential.get("verify_tls"),
                default=True,
            ),
        }
        token = self.credential.get("token") or self.credential.get("password")
        if token:
            credential_data["token"] = "${" + self._token_env_name() + "}"
        return credential_data

    def env_config(self, *args, **kwargs):
        token = self.credential.get("token") or self.credential.get("password")
        if not token:
            return {}
        return {self._token_env_name(): token}

    def get_hosts(self):
        if self.instance.instances:
            host = self.instance.instances[0].get("ip_addr", "")
        else:
            host = self.instance.ip_range
        return "host", host

    def _token_env_name(self):
        return f"PASSWORD_token_{self._instance_id}"
