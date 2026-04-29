from apps.cmdb.collection.collect_plugin.host import HostCollectMetrics
from apps.cmdb.collection.plugins.community.host.base import BaseHostCollectionPlugin


class HostCollectionPlugin(BaseHostCollectionPlugin):
    supported_model_id = "host"
    metric_names = ("host_info_gauge", "host_proc_usage_info_gauge")
    field_mapping = {
        "inst_name": HostCollectMetrics.set_display_inst_name,
        "ip_addr": HostCollectMetrics.set_ip_addr,
        "cloud": HostCollectMetrics.set_cloud,
        "hostname": "hostname",
        "os_type": HostCollectMetrics.set_os_type,
        "os_name": "os_name",
        "os_version": "os_version",
        "os_bit": "os_bits",
        "cpu_model": "cpu_model",
        "cpu_core": (HostCollectMetrics.transform_int, "cpu_cores"),
        "memory": (HostCollectMetrics.transform_int, "memory_gb"),
        "disk": (HostCollectMetrics.transform_int, "disk_gb"),
        "cpu_arch": HostCollectMetrics.set_cpu_arch,
        "inner_mac": (HostCollectMetrics.format_mac, "mac_address"),
        "proc": HostCollectMetrics.get_host_proc,
    }
