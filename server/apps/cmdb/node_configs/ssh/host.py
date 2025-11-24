# -- coding: utf-8 --
# @File: host.py
# @Time: 2025/11/13 14:27
# @Author: windyzhao
from apps.cmdb.node_configs.base import BaseNodeParams
from apps.cmdb.node_configs.ssh.base import SSHNodeParamsMixin


class HostNodeParams(SSHNodeParamsMixin, BaseNodeParams):
    supported_model_id = "host"  # 模型id
    plugin_name = "host_info"  # 插件名称
