# -- coding: utf-8 --
"""FusionInsight NodeParams：补齐采集下发链路。"""
from apps.cmdb.node_configs.base import BaseNodeParams
from apps.cmdb.node_configs.cloud._cloud_base import CloudAkSkNodeParamsMixin


class FusionInsightNodeParams(CloudAkSkNodeParamsMixin, BaseNodeParams):
    supported_model_id = "fusioninsight"
    plugin_name = "fusioninsight_info"
