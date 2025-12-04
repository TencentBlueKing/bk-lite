# -- coding: utf-8 --
# @File: etcd.py
# @Time: 2025/11/13 14:28
# @Author: windyzhao
from apps.cmdb.node_configs.base import BaseNodeParams
from apps.cmdb.node_configs.ssh.base import SSHNodeParamsMixin


class EtcdNodeParams(SSHNodeParamsMixin, BaseNodeParams):
    supported_model_id = "etcd"
    plugin_name = "etcd_info"
