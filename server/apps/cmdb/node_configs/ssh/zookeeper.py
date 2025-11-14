# -- coding: utf-8 --
# @File: zookeeper.py
# @Time: 2025/11/13 14:29
# @Author: windyzhao
from apps.cmdb.node_configs.base import BaseNodeParams
from apps.cmdb.node_configs.ssh.base import SSHNodeParamsMixin


class ZookeeperNodeParams(SSHNodeParamsMixin, BaseNodeParams):
    supported_model_id = "zookeeper"
    plugin_name = "zookeeper_info"
