# -- coding: utf-8 --
# @File: tongweb.py
# @Time: 2025/11/13 14:28
# @Author: windyzhao
from apps.cmdb.node_configs.base import BaseNodeParams
from apps.cmdb.node_configs.ssh.base import SSHNodeParamsMixin


class TongWebNodeParams(SSHNodeParamsMixin, BaseNodeParams):
    supported_model_id = "tongweb"
    plugin_name = "tongweb_info"
