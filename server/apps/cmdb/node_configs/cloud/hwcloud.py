# -- coding: utf-8 --
"""华为云 NodeParams：补齐采集下发链路。"""
from apps.cmdb.node_configs.base import BaseNodeParams
from apps.cmdb.node_configs.cloud._cloud_base import CloudAkSkNodeParamsMixin


class HwCloudNodeParams(CloudAkSkNodeParamsMixin, BaseNodeParams):
    supported_model_id = "hwcloud"
    plugin_name = "huaweicloud_info"
