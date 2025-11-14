# -- coding: utf-8 --
# @File: kafka.py
# @Time: 2025/11/13 14:29
# @Author: windyzhao
from apps.cmdb.node_configs.base import BaseNodeParams
from apps.cmdb.node_configs.ssh.base import SSHNodeParamsMixin


class KafkaNodeParams(SSHNodeParamsMixin, BaseNodeParams):
    supported_model_id = "kafka"
    plugin_name = "kafka_info"