from functools import partial

from apps.cmdb.collection.collect_plugin.middleware import MiddlewareCollectMetrics
from apps.cmdb.collection.plugins.community.middleware.base import BaseMiddlewareCollectionPlugin


class WeblogicCollectionPlugin(BaseMiddlewareCollectionPlugin):
    supported_model_id = "weblogic"
    metric_names = ("weblogic_info_gauge",)
    field_mapping = {
        "inst_name": MiddlewareCollectMetrics.get_inst_name,
        "ip_addr": "ip_addr",
        "port": MiddlewareCollectMetrics.get_port,
        "version": partial(MiddlewareCollectMetrics.pick_value, keys=("version", "domain_version")),
        "name": "name",
        "console_context_path": "console_context_path",
        "console_enabled": "console_enabled",
        "md_home": partial(MiddlewareCollectMetrics.pick_value, keys=("md_home", "domain_path")),
        "root_dir": partial(MiddlewareCollectMetrics.pick_value, keys=("root_dir", "domain_path")),
        "weblogic_home": partial(MiddlewareCollectMetrics.pick_value, keys=("weblogic_home", "Dweblogic_home_path", "wlst_path")),
        "application_name": "application_name",
        "admin_server_name": "admin_server_name",
        "domain_version": "domain_version",
        "java_version": "java_version",
        "assos": MiddlewareCollectMetrics.get__host_assos,
    }
