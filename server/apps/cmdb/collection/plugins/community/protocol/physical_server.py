from apps.cmdb.collection.collect_plugin.host import HostCollectMetrics
from apps.cmdb.collection.nic_inventory import is_ingestible_nic
from apps.cmdb.collection.physical_server_identity import normalize_physical_server_ip, resolve_physical_server_inst_name
from apps.cmdb.collection.plugins.base import bind_collection_mapping
from apps.cmdb.collection.plugins.community.protocol.base import BaseProtocolCollectionPlugin

_SERVER_CPU_ARCH = (
    ("x86_64", "x64"),
    ("arm64", "arm64"),
    ("aarch64", "arm64"),
    ("i386", "x86"),
    ("i486", "x86"),
    ("i586", "x86"),
    ("i686", "x86"),
    ("armv7l", "arm"),
    ("armv8l", "arm64"),
)


class PhysicalServerProtocolCollectionPlugin(BaseProtocolCollectionPlugin):
    def get_inst_name(self, data, *args, **kwargs):
        return resolve_physical_server_inst_name(data, fallback=self.inst_name)

    def set_physical_server_component_parent(self, data, *args, **kwargs):
        return normalize_physical_server_ip(data.get("self_device")) or normalize_physical_server_ip(self.inst_name)

    def set_physical_server_component_inst_name(self, data, *args, **kwargs):
        normalized_data = {
            **data,
            "self_device": self.set_physical_server_component_parent(data),
        }
        return HostCollectMetrics.set_component_inst_name(self, normalized_data)

    def set_physical_server_asso_instances(self, data, *args, **kwargs):
        normalized_data = {
            **data,
            "self_device": self.set_physical_server_component_parent(data),
        }
        return HostCollectMetrics.set_asso_instances(self, normalized_data, *args, **kwargs)

    def set_physical_server_nic_asso_instances(self, data, *args, **kwargs):
        normalized_data = {
            **data,
            "self_device": self.set_physical_server_component_parent(data),
        }
        return HostCollectMetrics.set_nic_asso_instances(self, normalized_data, *args, **kwargs)

    def set_redfish_cpu_arch(self, data, *args, **kwargs):
        token = str(data.get("cpu_arch") or "").strip().lower()
        if not token:
            return ""
        for name, arch_id in _SERVER_CPU_ARCH:
            if name in token:
                return arch_id
        return ""

    def set_nic_inst_name(self, data, *args, **kwargs):
        return HostCollectMetrics.set_nic_inst_name(self, data, *args, **kwargs)

    def set_nic_mac(self, data, *args, **kwargs):
        return HostCollectMetrics.set_nic_mac(self, data, *args, **kwargs)

    supported_model_id = "physcial_server"
    metric_names = (
        "physcial_server_info_gauge",
        "disk_info_gauge",
        "memory_info_gauge",
        "nic_info_gauge",
        "gpu_info_gauge",
        "storage_controller_info_gauge",
        "psu_info_gauge",
    )
    field_mapping = {
        "ip_addr": "ip_addr",
        "serial_number": "serial_number",
        "model": "model",
        "brand": "brand",
        "asset_code": "asset_code",
        "board_vendor": "board_vendor",
        "board_model": "board_model",
        "board_serial": "board_serial",
        "cpu_vendor": "cpu_vendor",
        "cpu_model": "cpu_model",
        "cpu_core": (HostCollectMetrics.transform_int, "cpu_cores"),
        "cpu_threads": (HostCollectMetrics.transform_int, "cpu_threads"),
        "cpu_arch": set_redfish_cpu_arch,
        "power_state": "power_state",
        "health": "health",
        "inst_name": get_inst_name,
    }
    related_field_mappings = {
        "memory": {
            "inst_name": set_physical_server_component_inst_name,
            "self_device": set_physical_server_component_parent,
            "mem_locator": "mem_locator",
            "mem_part_number": "mem_part_number",
            "mem_type": "mem_type",
            "mem_size": (HostCollectMetrics.transform_unit_int, "mem_size"),
            "mem_sn": "mem_sn",
            "assos": set_physical_server_asso_instances,
        },
        "gpu": {
            "inst_name": set_physical_server_component_inst_name,
            "self_device": set_physical_server_component_parent,
            "gpu_name": "gpu_name",
            "gpu_type": "gpu_type",
            "gpu_desc": "gpu_desc",
            "assos": set_physical_server_asso_instances,
        },
        "disk": {
            "inst_name": set_physical_server_component_inst_name,
            "self_device": set_physical_server_component_parent,
            "disk_vendor": "disk_vendor",
            "disk": (HostCollectMetrics.transform_unit_int, "disk"),
            "disk_type": "disk_type",
            "disk_sn": "disk_sn",
            "health": "health",
            "disk_life_percent": (HostCollectMetrics.transform_int, "disk_life_percent"),
            "assos": set_physical_server_asso_instances,
        },
        "nic": {
            "inst_name": set_nic_inst_name,
            "self_device": set_physical_server_component_parent,
            "nic_pci_addr": "nic_pci_addr",
            "nic_type": "nic_type",
            "nic_vendor": "nic_vendor",
            "nic_model": "nic_model",
            "nic_iface": "nic_iface",
            "nic_speed_mbps": (HostCollectMetrics.transform_int, "nic_speed_mbps"),
            "nic_mac": set_nic_mac,
            "assos": set_physical_server_nic_asso_instances,
        },
        "storage_controller": {
            "inst_name": set_physical_server_component_inst_name,
            "self_device": set_physical_server_component_parent,
            "sc_id": "sc_id",
            "sc_name": "sc_name",
            "sc_vendor": "sc_vendor",
            "sc_model": "sc_model",
            "sc_sn": "sc_sn",
            "sc_firmware": "sc_firmware",
            "health": "health",
            "assos": set_physical_server_asso_instances,
        },
        "psu": {
            "inst_name": set_physical_server_component_inst_name,
            "self_device": set_physical_server_component_parent,
            "psu_name": "psu_name",
            "psu_vendor": "psu_vendor",
            "psu_model": "psu_model",
            "psu_sn": "psu_sn",
            "psu_capacity_watts": (HostCollectMetrics.transform_int, "psu_capacity_watts"),
            "health": "health",
            "assos": set_physical_server_asso_instances,
        },
    }

    @property
    def model_field_mapping(self):
        mappings = {self.model_id: bind_collection_mapping(self, self.field_mapping)}
        for model_id, mapping in self.related_field_mappings.items():
            mappings[model_id] = bind_collection_mapping(self, mapping)
        return mappings

    def format_data(self, data):
        if not isinstance(data, dict):
            return
        for index_data in data.get("result", []):
            metric_name = index_data["metric"].get("__name__")
            if metric_name not in self.metric_names:
                continue
            if index_data["metric"].get("collect_status", "failed") == "failed":
                continue
            self.collection_metrics_dict[metric_name].append(index_data["metric"])

    @staticmethod
    def _normalize_field_value(value):
        if isinstance(value, str):
            return value.strip()
        return value

    @staticmethod
    def _should_skip_mapped_value(field, value):
        if field in ("disk", "mem_size") and value == 0:
            return True
        return value in (None, "")

    def _map_metric_row(self, index_data, model_id, mapping):
        row = dict(index_data)
        if "model_id" not in row:
            row["model_id"] = model_id

        data = {}
        for field, key_or_func in mapping.items():
            if isinstance(key_or_func, tuple):
                transform, source_field = key_or_func
                if source_field not in index_data:
                    continue
                raw_value = self._normalize_field_value(index_data[source_field])
                if raw_value in (None, ""):
                    continue
                try:
                    value = transform(raw_value)
                except (KeyError, ValueError, TypeError):
                    continue
                if self._should_skip_mapped_value(field, value):
                    continue
                data[field] = value
            elif callable(key_or_func):
                try:
                    value = key_or_func(row, model_id=model_id)
                except Exception:
                    continue
                value = self._normalize_field_value(value)
                if self._should_skip_mapped_value(field, value):
                    continue
                data[field] = value
            else:
                value = self._normalize_field_value(index_data.get(key_or_func))
                if self._should_skip_mapped_value(field, value):
                    continue
                data[field] = value
        return data

    def format_metrics(self):
        self.result = {}
        for metric_key in self.metric_names:
            model_id = metric_key[: -len("_info_gauge")]
            mapping = self.model_field_mapping.get(model_id, {})
            if not mapping:
                continue

            result = []
            for index_data in self.collection_metrics_dict.get(metric_key, []):
                if model_id == "nic" and not is_ingestible_nic(index_data.get("nic_iface"), index_data.get("nic_mac")):
                    continue

                data = self._map_metric_row(index_data, model_id, mapping)
                if model_id == self.model_id:
                    if data:
                        result.append(data)
                elif data.get("inst_name"):
                    result.append(data)

            if result:
                self.result[model_id] = result


# 保留旧导入名，避免企业扩展直接导入时中断。
PhysicalServerIPMICollectionPlugin = PhysicalServerProtocolCollectionPlugin
