# -- coding: utf-8 --
# @File: db2.py
# @Time: 2025/11/13 14:28
# @Author: windyzhao
from apps.cmdb.node_configs.base import BaseNodeParams
from apps.cmdb.node_configs.ssh.base import SSHNodeParamsMixin


class DB2NodeParams(SSHNodeParamsMixin, BaseNodeParams):
    supported_model_id = "db2"
    plugin_name = "db2_info"
