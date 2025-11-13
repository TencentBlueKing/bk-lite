# -- coding: utf-8 --
# @File: aliyun.py
# @Time: 2025/11/12 15:04
# @Author: windyzhao
from apps.cmdb.collect_tasks.bash import BaseCollect
from apps.cmdb.collection.collect_plugin.aliyun import AliyunCollectMetrics


class AliyunCollect(BaseCollect):
    COLLECT_PLUGIN = AliyunCollectMetrics
