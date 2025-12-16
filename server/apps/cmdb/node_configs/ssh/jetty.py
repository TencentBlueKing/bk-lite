# -- coding: utf-8 --
# @File: jetty.py
# @Time: 2025/11/13 14:28
# @Author: windyzhao
from apps.cmdb.node_configs.base import BaseNodeParams
from apps.cmdb.node_configs.ssh.base import SSHNodeParamsMixin


class JettyNodeParams(SSHNodeParamsMixin, BaseNodeParams):
    supported_model_id = "jetty"
    plugin_name = "jetty_info"
