# -- coding: utf-8 --
# @File: protocol.py
# @Time: 2025/11/12 14:54
# @Author: windyzhao
from apps.cmdb.collect_tasks.bash import BaseCollect
from apps.cmdb.collection.collect_plugin.protocol import ProtocolCollectMetrics


class ProtocolTaskCollect(BaseCollect):
    COLLECT_PLUGIN = ProtocolCollectMetrics
