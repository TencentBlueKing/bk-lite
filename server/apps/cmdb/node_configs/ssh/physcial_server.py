# -- coding: utf-8 --
# @File: physcial_server.py
# @Time: 2025/12/08 14:27
# @Author: roger
from apps.cmdb.node_configs.base import BaseNodeParams
from apps.cmdb.node_configs.ssh.base import SSHNodeParamsMixin


class PhyscialServerNodeParams(SSHNodeParamsMixin, BaseNodeParams):
    supported_model_id = "physcial_server"  # 模型id
    plugin_name = "physcial_server_info"  # 插件名称
