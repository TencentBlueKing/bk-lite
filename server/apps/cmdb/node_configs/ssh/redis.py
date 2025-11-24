# -- coding: utf-8 --
# @File: redis.py
# @Time: 2025/11/13 14:28
# @Author: windyzhao
from apps.cmdb.node_configs.base import BaseNodeParams
from apps.cmdb.node_configs.ssh.base import SSHNodeParamsMixin


class RedisNodeParams(SSHNodeParamsMixin, BaseNodeParams):
    supported_model_id = "redis"
    plugin_name = "redis_info"