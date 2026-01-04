# -- coding: utf-8 --
# @File: databases.py
# @Time: 2025/11/12 15:11
# @Author: windyzhao
from apps.cmdb.collection.collect_tasks.base import BaseCollect
from apps.cmdb.collection.collect_plugin.databases import DBCollectCollectMetrics


class DBCollect(BaseCollect):
    COLLECT_PLUGIN = DBCollectCollectMetrics
