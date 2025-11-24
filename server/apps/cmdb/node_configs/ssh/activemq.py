# -- coding: utf-8 --
# @File: activemq.py
# @Time: 2025/11/13 14:28
# @Author: windyzhao
from apps.cmdb.node_configs.base import BaseNodeParams
from apps.cmdb.node_configs.ssh.base import SSHNodeParamsMixin


class ActiveMQNodeParams(SSHNodeParamsMixin, BaseNodeParams):
    supported_model_id = "activemq"
    plugin_name = "activemq_info"
