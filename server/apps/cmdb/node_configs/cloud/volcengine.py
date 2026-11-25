# -- coding: utf-8 --
"""火山引擎 NodeParams。注册键是 volcengine，任务模型是 volcengine_account。"""
from apps.cmdb.node_configs.base import BaseNodeParams
from apps.cmdb.node_configs.cloud._cloud_base import CloudAkSkNodeParamsMixin


class VolcengineNodeParams(CloudAkSkNodeParamsMixin, BaseNodeParams):
    supported_model_id = "volcengine"
    plugin_name = "volcengine_info"
