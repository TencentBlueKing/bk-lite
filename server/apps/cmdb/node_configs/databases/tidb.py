# -- coding: utf-8 --
# @File: tidb.py
# @Time: 2025/11/13 14:28
# @Author: windyzhao
from apps.cmdb.node_configs.base import BaseNodeParams
from apps.cmdb.node_configs.ssh.base import SSHNodeParamsMixin


class TiDBNodeParams(SSHNodeParamsMixin, BaseNodeParams):
    supported_model_id = "tidb"
    plugin_name = "tidb_info"
