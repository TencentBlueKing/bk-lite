# -- coding: utf-8 --
# @File: network.py
# @Time: 2025/11/12 14:51
# @Author: windyzhao
from apps.cmdb.collect_tasks.bash import BaseCollect
from apps.cmdb.collection.collect_plugin.network import CollectNetworkMetrics


class NetworkCollect(BaseCollect):
    COLLECT_PLUGIN = CollectNetworkMetrics
