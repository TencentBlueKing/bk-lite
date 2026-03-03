# -- coding: utf-8 --
# @File: consul.py
# @Time: 2026/1/12

from apps.cmdb.node_configs.base import BaseNodeParams
from apps.cmdb.node_configs.ssh.base import SSHNodeParamsMixin


class ConsulNodeParams(SSHNodeParamsMixin, BaseNodeParams):
    supported_model_id = "consul"
    plugin_name = "consul_info"