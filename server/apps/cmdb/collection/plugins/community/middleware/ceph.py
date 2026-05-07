from functools import partial

from apps.cmdb.collection.collect_plugin.middleware import MiddlewareCollectMetrics
from apps.cmdb.collection.plugins.community.middleware.base import BaseMiddlewareCollectionPlugin


class CephCollectionPlugin(BaseMiddlewareCollectionPlugin):
    supported_model_id = "ceph"
    metric_names = ("ceph_info_gauge",)
    field_mapping = {
        "inst_name": MiddlewareCollectMetrics.get_inst_name,
        "ip_addr": "ip_addr",
        "port": MiddlewareCollectMetrics.get_port,
        "version": "version",
        "role": "role",
        "install_path": "install_path",
        "config_file": partial(MiddlewareCollectMetrics.pick_value, keys=("config_file", "conf_file")),
        "cmdline": "cmdline",
        "ceph_exe": "ceph_exe",
    }
