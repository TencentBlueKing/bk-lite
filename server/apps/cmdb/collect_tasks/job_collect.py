# -- coding: utf-8 --
# @File: job_collect.py
# @Time: 2025/11/12 15:09
# @Author: windyzhao
from apps.cmdb.collect_tasks.databases import DBCollect
from apps.cmdb.collect_tasks.host import HostCollect
from apps.cmdb.collect_tasks.middleware import MiddlewareCollect
from apps.cmdb.constants.constants import CollectPluginTypes


class JobCollect(object):
    def __init__(self, task, default_metrics=None):
        self.task = task
        self.default_metrics = default_metrics

    @property
    def collect_manage(self):
        result = {
            CollectPluginTypes.HOST: self.collect_host,
            CollectPluginTypes.DB: self.collect_db,
            CollectPluginTypes.MIDDLEWARE: self.collect_middleware
        }
        return result

    def get_instance(self):
        instance = self.task.instances[0] if self.task.instances else None
        return instance

    def collect_host(self):
        data = HostCollect(self.task.id)()
        return data

    def collect_middleware(self):
        data = MiddlewareCollect(self.task.id)()
        return data

    def collect_db(self):
        return DBCollect(self.task.id)()

    def main(self):
        return self.collect_manage[self.task.task_type]()
