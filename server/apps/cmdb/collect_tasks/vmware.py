# -- coding: utf-8 --
# @File: vmware.py
# @Time: 2025/11/12 14:51
# @Author: windyzhao
from apps.cmdb.collect_tasks.bash import BaseCollect
from apps.cmdb.collection.collect_plugin.vmware import CollectVmwareMetrics


class VmwareCollect(BaseCollect):
    COLLECT_PLUGIN = CollectVmwareMetrics
