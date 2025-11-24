# -- coding: utf-8 --
# @File: aws.py
# @Time: 2025/11/12 15:09
# @Author: windyzhao
from apps.cmdb.collect_tasks.bash import BaseCollect
from apps.cmdb.collection.collect_plugin.aws import AWSCollectMetrics


class AWSCollect(BaseCollect):
    COLLECT_PLUGIN = AWSCollectMetrics
