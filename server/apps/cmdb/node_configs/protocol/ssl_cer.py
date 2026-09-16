import json

from apps.cmdb.constants.constants import CollectDriverTypes
from apps.cmdb.node_configs.base import BaseNodeParams


class SslCerNodeParams(BaseNodeParams):
    supported_model_id = "ssl_cer"
    supported_driver_type = CollectDriverTypes.PROTOCOL
    plugin_name = "ssl_cer_info"
    host_field = "domain"
    default_port = 443

    def set_credential(self, *args, **kwargs):
        targets = []
        for instance in self.instance.instances or []:
            if not isinstance(instance, dict):
                continue
            targets.append(
                {
                    "inst_name": str(instance.get("inst_name") or "").strip(),
                    "domain": str(instance.get("domain") or "").strip(),
                }
            )
        return {
            "port": self.default_port,
            "ssl_cer_targets": json.dumps(targets, ensure_ascii=False),
        }

    def env_config(self, *args, **kwargs):
        return {}

    def get_hosts(self):
        hosts = []
        for instance in self.instance.instances or []:
            domain = str((instance or {}).get(self.host_field) or "").strip()
            if domain:
                hosts.append(domain)
        return "hosts", ",".join(hosts)
