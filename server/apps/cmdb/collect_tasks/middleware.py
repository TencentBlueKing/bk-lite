# -- coding: utf-8 --
# @File: middleware.py
# @Time: 2025/11/12 15:10
# @Author: windyzhao
from apps.cmdb.collect_tasks.bash import BaseCollect
from apps.cmdb.collection.collect_plugin.middleware import MiddlewareCollectMetrics


class MiddlewareCollect(BaseCollect):
    COLLECT_PLUGIN = MiddlewareCollectMetrics
