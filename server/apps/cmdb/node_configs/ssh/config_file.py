# -- coding: utf-8 --

from apps.cmdb.node_configs.base import BaseNodeParams
from apps.cmdb.node_configs.ssh.base import SSHNodeParamsMixin

class ConfigFileNodeParams(SSHNodeParamsMixin, BaseNodeParams):
    supported_model_id = "config_file"
    plugin_name = "config_file_info"
    interval = 10 * 60

    def _get_instance_host(self, instance):
        if not isinstance(instance, dict):
            return ""
        connect_ip = str(instance.get(self.host_field) or instance.get("ip_addr") or instance.get("host") or "").strip()
        if not connect_ip:
            return ""

        inst_name = str(instance.get("inst_name") or "").strip()
        if inst_name.startswith(f"{connect_ip}[") and inst_name.endswith("]"):
            return inst_name

        cloud_label = str(instance.get("cloud_id") or instance.get("cloud") or "").strip()
        if cloud_label:
            return f"{connect_ip}[{cloud_label}]"
        return connect_ip

    @staticmethod
    def _get_connect_ip(host):
        host_str = str(host or "").strip()
        if not host_str:
            return ""
        return host_str.split("[", 1)[0].strip()

    @staticmethod
    def _get_instance_id(instance):
        if not isinstance(instance, dict):
            return ""
        return str(instance.get("_id") or instance.get("id") or "")

    def _get_single_target_instance(self):
        instances = self.instance.instances or []
        if len(instances) != 1:
            return {}
        target_instance = instances[0]
        return target_instance if isinstance(target_instance, dict) else {}

    def get_hosts(self):
        if self.instance.instances:
            hosts = ",".join(filter(None, (self._get_instance_host(instance) for instance in self.instance.instances)))
        else:
            hosts = self.instance.ip_range
        return "hosts", hosts

    def set_credential(self, *args, **kwargs):
        credential_data = super().set_credential(*args, **kwargs)
        params = self.instance.params or {}
        target_instance = self._get_single_target_instance()
        target_host = self._get_instance_host(target_instance)
        credential_data.update(
            {
                "config_file_path": params.get("config_file_path", ""),
                "collect_task_id": self.instance.id,
                "execution_id": self.instance.task_id,
                "target_model_id": target_instance.get("model_id") or params.get("target_model_id") or "host",
                "callback_subject": "receive_config_file_result",
            }
        )
        if target_instance:
            credential_data.update(
                {
                    "target_instance_id": self._get_instance_id(target_instance),
                    "connect_ip": self._get_connect_ip(target_host),
                }
            )
        return credential_data
