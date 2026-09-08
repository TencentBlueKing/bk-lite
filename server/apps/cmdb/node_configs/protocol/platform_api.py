from urllib.parse import urlsplit

from apps.cmdb.constants.constants import CollectDriverTypes
from apps.cmdb.node_configs.base import BaseNodeParams


def _as_bool(value, default=True):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


class PlatformApiNodeParamsMixin:
    default_port = 443

    def _username_env_name(self):
        return f"PASSWORD_username_{self._instance_id}"

    def _password_env_name(self):
        return f"PASSWORD_password_{self._instance_id}"

    def _endpoint(self):
        params = getattr(self.instance, "params", None) or {}
        if params.get("host"):
            raw_host = params["host"]
        elif self.instance.instances:
            first = self.instance.instances[0] or {}
            raw_host = first.get("endpoint") or first.get("ip_addr") or first.get("host") or ""
        else:
            raw_host = self.instance.ip_range

        parsed = urlsplit(raw_host if "://" in str(raw_host) else f"//{raw_host}")
        try:
            port = parsed.port
        except ValueError:
            port = None
        return {
            "host": parsed.hostname or str(raw_host).strip("/"),
            "scheme": parsed.scheme or None,
            "port": port,
        }

    def get_hosts(self):
        return "host", self._endpoint()["host"]

    def set_credential(self, *args, **kwargs):
        endpoint = self._endpoint()
        return {
            "username": "${" + self._username_env_name() + "}",
            "password": "${" + self._password_env_name() + "}",
            "scheme": (self.credential.get("scheme") or endpoint["scheme"] or "https"),
            "port": (self.credential.get("port") or endpoint["port"] or self.default_port),
            "verify_tls": _as_bool(
                self.credential.get("verify_tls"),
                default=True,
            ),
        }

    def env_config(self, *args, **kwargs):
        return {
            self._username_env_name(): (self.credential.get("username") or self.credential.get("accessKey", "")),
            self._password_env_name(): (self.credential.get("password") or self.credential.get("accessSecret", "")),
        }


class FusionInsightNodeParams(PlatformApiNodeParamsMixin, BaseNodeParams):
    supported_model_id = "fusioninsight"
    supported_driver_type = CollectDriverTypes.PROTOCOL
    plugin_name = "fusioninsight_info"
    default_port = 443


class OceanStorNodeParams(PlatformApiNodeParamsMixin, BaseNodeParams):
    supported_model_id = "storage"
    supported_driver_type = CollectDriverTypes.PROTOCOL
    plugin_name = "oceanstor_info"
    default_port = 8088


class DellUnityNodeParams(PlatformApiNodeParamsMixin, BaseNodeParams):
    supported_model_id = "dell_unity"
    supported_driver_type = CollectDriverTypes.PROTOCOL
    plugin_name = "dell_unity_info"
    default_port = 443


class NetAppOntapNodeParams(PlatformApiNodeParamsMixin, BaseNodeParams):
    supported_model_id = "netapp_ontap"
    supported_driver_type = CollectDriverTypes.PROTOCOL
    plugin_name = "netapp_ontap_info"
    default_port = 443
