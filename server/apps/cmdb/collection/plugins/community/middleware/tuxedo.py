from apps.cmdb.collection.collect_plugin.middleware import MiddlewareCollectMetrics
from apps.cmdb.collection.plugins.community.middleware.base import BaseMiddlewareCollectionPlugin


class TuxedoCollectionPlugin(BaseMiddlewareCollectionPlugin):
    supported_model_id = "tuxedo"
    metric_names = ("tuxedo_info_gauge",)
    field_mapping = {
        "inst_name": MiddlewareCollectMetrics.get_inst_name,
        "ip_addr": "ip_addr",
        "port": MiddlewareCollectMetrics.get_port,
        "version": "version",
        "install_path": "install_path",
        "bin_path": "bin_path",
        "conf_file": "conf_file",
        "domainid": "domainid",
        "ipckey": "ipckey",
        "lmid": "lmid",
        "patch_level": "patch_level",
        "maxdispatchthreads": "maxdispatchthreads",
        "mindispatchthreads": "mindispatchthreads",
    }
