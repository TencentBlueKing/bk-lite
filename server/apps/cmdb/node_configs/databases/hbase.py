# -- coding: utf-8 --
# @File: hbase.py
# @Time: 2025/11/13 14:28
# @Author: windyzhao
from apps.cmdb.node_configs.base import BaseNodeParams
from apps.cmdb.node_configs.ssh.base import SSHNodeParamsMixin


class HBaseNodeParams(SSHNodeParamsMixin, BaseNodeParams):
    supported_model_id = "hbase"
    plugin_name = "hbase_info"
