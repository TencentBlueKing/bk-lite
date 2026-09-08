from apps.cmdb.collection.collect_plugin.host import HostCollectMetrics
from apps.cmdb.collection.physical_server_identity import normalize_physical_server_ip, resolve_physical_server_inst_name
from apps.cmdb.collection.plugins.community.host.base import BaseHostCollectionPlugin


class PhysicalServerCollectionPlugin(BaseHostCollectionPlugin):
    def set_physical_server_inst_name(self, data, *args, **kwargs):
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

    supported_model_id = "physcial_server"
    metric_names = (
        "physcial_server_info_gauge",
        "disk_info_gauge",
        "memory_info_gauge",
        "nic_info_gauge",
        "gpu_info_gauge",
    )
    field_mapping = {
        "inst_name": set_physical_server_inst_name,
        "serial_number": "serial_number",
        "cpu_vendor": "cpu_vendor",
        "cpu_model": "cpu_model",
        "cpu_core": (HostCollectMetrics.transform_int, "cpu_cores"),
        "cpu_threads": (HostCollectMetrics.transform_int, "cpu_threads"),
        "cpu_arch": HostCollectMetrics.set_serverarch_type,
        "board_vendor": "board_vendor",
        "board_model": "board_model",
        "board_serial": "board_serial",
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
            "assos": set_physical_server_asso_instances,
        },
        "nic": {
            "inst_name": HostCollectMetrics.set_nic_inst_name,
            "self_device": set_physical_server_component_parent,
            "nic_pci_addr": "nic_pci_addr",
            "nic_type": "nic_type",
            "nic_vendor": "nic_vendor",
            "nic_model": "nic_model",
            "nic_iface": "nic_iface",
            "nic_mac": HostCollectMetrics.set_nic_mac,
            "assos": set_physical_server_nic_asso_instances,
        },
    }
