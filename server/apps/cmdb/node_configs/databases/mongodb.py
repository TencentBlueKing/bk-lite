# -- coding: utf-8 --
# @File: mongodb.py
# @Time: 2025/11/13 14:28
# @Author: windyzhao
from apps.cmdb.node_configs.base import BaseNodeParams
from apps.cmdb.node_configs.ssh.base import SSHNodeParamsMixin


class MongoDBParams(SSHNodeParamsMixin, BaseNodeParams):
    supported_model_id = "mongodb"
    plugin_name = "mongodb_info"
