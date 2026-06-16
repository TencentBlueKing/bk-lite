from apps.cmdb.collection.collect_plugin.middleware import MiddlewareCollectMetrics
from apps.cmdb.collection.plugins.community.middleware.base import BaseMiddlewareCollectionPlugin


class KeepalivedCollectionPlugin(BaseMiddlewareCollectionPlugin):
    # 模型 model_id 为 "keepalive"（见 model_config.xlsx models 表）；
    # stargazer 产出的指标仍是 keepalived_info_gauge，故 metric_names 不变。
    supported_model_id = "keepalive"
    metric_names = ("keepalived_info_gauge",)
    field_mapping = {
        "inst_name": MiddlewareCollectMetrics.get_keepalived_inst_name,
        "ip_addr": "ip_addr",
        "bk_obj_id": "bk_obj_id",
        "version": "version",
        "priority": "priority",
        "state": "state",
        "virtual_router_id": "virtual_router_id",
        "user_name": "user_name",
        "install_path": "install_path",
        "config_file": "config_file",
    }
