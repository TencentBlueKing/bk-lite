# -- coding: utf-8 --
# @File: pgsql.py
# @Time: 2025/11/13 14:28
# @Author: windyzhao
from apps.cmdb.node_configs.base import BaseNodeParams
from apps.cmdb.node_configs.ssh.base import SSHNodeParamsMixin


class PgsqlNodeParams(SSHNodeParamsMixin, BaseNodeParams):
    supported_model_id = "postgresql"
    plugin_name = "pgsql_info"
