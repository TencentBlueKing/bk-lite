# -- coding: utf-8 --
# @File: k8s.py
# @Time: 2025/11/12 14:42
# @Author: windyzhao
from apps.cmdb.collect_tasks.bash import BaseCollect
from apps.cmdb.collection.collect_plugin.k8s import CollectK8sMetrics


class K8sCollect(BaseCollect):
    COLLECT_PLUGIN = CollectK8sMetrics
