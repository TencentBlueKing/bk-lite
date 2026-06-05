# -- coding: utf-8 --
# @File: protocol_collect.py
# @Time: 2025/11/12 14:40
# @Author: windyzhao
from apps.cmdb.collection.collect_tasks.registry import RegisteredCollect


class ProtocolCollect(object):
    def __init__(self, task, default_metrics=None):
        self.task = task
        self.default_metrics = default_metrics

    def main(self):
        return RegisteredCollect(self.task.id, self.default_metrics, task=self.task)()
