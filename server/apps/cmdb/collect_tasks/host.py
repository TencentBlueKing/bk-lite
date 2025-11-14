# -- coding: utf-8 --
# @File: host.py
# @Time: 2025/11/12 15:10
# @Author: windyzhao
from apps.cmdb.collect_tasks.bash import BaseCollect
from apps.cmdb.collection.collect_plugin.host import HostCollectMetrics


class HostCollect(BaseCollect):
    COLLECT_PLUGIN = HostCollectMetrics
