from apps.cmdb.collection.collect_plugin.host import HostCollectMetrics
from apps.cmdb.collection.plugins.community.host.base import BaseHostCollectionPlugin


class PhysicalServerCollectionPlugin(BaseHostCollectionPlugin):
    supported_model_id = "physcial_server"
    metric_names = (
        "physcial_server_info_gauge",
        "disk_info_gauge",
        "memory_info_gauge",
        "nic_info_gauge",
        "gpu_info_gauge",
    )
    field_mapping = {
        "inst_name": HostCollectMetrics.set_inst_name,
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
            "inst_name": HostCollectMetrics.set_component_inst_name,
            "self_device": "self_device",
            "mem_locator": "mem_locator",
            "mem_part_number": "mem_part_number",
            "mem_type": "mem_type",
            "mem_size": (HostCollectMetrics.transform_unit_int, "mem_size"),
            "mem_sn": "mem_sn",
            "assos": HostCollectMetrics.set_asso_instances,
        },
        "gpu": {
            "inst_name": HostCollectMetrics.set_component_inst_name,
            "self_device": "self_device",
            "gpu_name": "gpu_name",
            "gpu_type": "gpu_type",
            "gpu_desc": "gpu_desc",
            "assos": HostCollectMetrics.set_asso_instances,
        },
        "disk": {
            "inst_name": HostCollectMetrics.set_component_inst_name,
            "self_device": "self_device",
            "disk_vendor": "disk_vendor",
            "disk": (HostCollectMetrics.transform_unit_int, "disk"),
            "disk_type": "disk_type",
            "disk_sn": "disk_sn",
            "assos": HostCollectMetrics.set_asso_instances,
        },
        "nic": {
            "inst_name": HostCollectMetrics.set_nic_inst_name,
            "self_device": "self_device",
            "nic_pci_addr": "nic_pci_addr",
            "nic_type": "nic_type",
            "nic_vendor": "nic_vendor",
            "nic_model": "nic_model",
            "nic_iface": "nic_iface",
            "nic_mac": HostCollectMetrics.set_nic_mac,
            "assos": HostCollectMetrics.set_nic_asso_instances,
        },
    }
