# -- coding: utf-8 --
# @File: qcloud.py
# @Time: 2025/11/12 15:08
# @Author: windyzhao
from apps.cmdb.collect_tasks.bash import BaseCollect
from apps.cmdb.collection.collect_plugin.qcloud import QCloudCollectMetrics


class QCloudCollect(BaseCollect):
    COLLECT_PLUGIN = QCloudCollectMetrics

