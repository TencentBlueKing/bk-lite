from functools import partial

from apps.cmdb.collection.collect_plugin.middleware import MiddlewareCollectMetrics
from apps.cmdb.collection.plugins.community.middleware.base import BaseMiddlewareCollectionPlugin


class MinioCollectionPlugin(BaseMiddlewareCollectionPlugin):
    """MinIO 对象存储采集（中间件脚本采集，对齐 Nginx/Kafka）。"""

    supported_model_id = "minio"
    metric_names = ("minio_info_gauge",)
    field_mapping = {
        "inst_name": MiddlewareCollectMetrics.get_inst_name,
        "ip_addr": "ip_addr",
        "port": "port",
        "version": "version",
        "bin_path": partial(MiddlewareCollectMetrics.pick_value, keys=("bin_path", "minio_path")),
        "data_path": partial(MiddlewareCollectMetrics.pick_value, keys=("data_path", "volumes")),
        "conf_path": partial(MiddlewareCollectMetrics.pick_value, keys=("conf_path", "config_path")),
        "console_port": "console_port",
        "deploy_mode": "deploy_mode",
        "region": "region",
        "start_args": "start_args",
    }
