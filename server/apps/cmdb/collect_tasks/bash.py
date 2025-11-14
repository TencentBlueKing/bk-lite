# -- coding: utf-8 --
# @File: bash.py
# @Time: 2025/11/12 14:41
# @Author: windyzhao
from apps.cmdb.collection.metrics_cannula import MetricsCannula
from apps.cmdb.models import CollectModels


class BaseCollect(object):
    COLLECT_PLUGIN = None

    def __init__(self, instance_id, default_metrics=None):
        self.task = CollectModels.objects.get(id=instance_id)
        self.default_metrics = default_metrics
        self.model_id, self.inst_name, self.organization, self.inst_id, self.filter_collect_task = self.format_params()

    def format_params(self):
        if not self.task.instances:
            return self.task.model_id, None, None, self.get_organization, None

        instance = self.task.instances[0]
        model_id = instance["model_id"]
        inst_name = instance["inst_name"]
        organization = instance["organization"]
        inst_id = instance["_id"]
        return model_id, inst_name, organization, inst_id, not self.task.is_host

    @property
    def get_organization(self):
        return self.task.params["organization"]

    @property
    def task_id(self):
        if self.task.is_k8s:
            return self.inst_name
        return self.task.id

    def run(self):
        if self.COLLECT_PLUGIN is None:
            raise NotImplementedError("Please implement the collect plugin")

        metrics_cannula = MetricsCannula(inst_id=self.inst_id, organization=self.organization, inst_name=self.inst_name,
                                         task_id=self.task_id, collect_plugin=self.COLLECT_PLUGIN,
                                         manual=bool(self.task.input_method), default_metrics=self.default_metrics,
                                         filter_collect_task=self.filter_collect_task)

        result = metrics_cannula.collect_controller()
        format_data = self.format_collect_data(result)

        return metrics_cannula.collect_data, format_data

    def format_collect_data(self, result):
        format_data = {"add": [], "update": [], "delete": [], "association": []}
        for value in result.values():
            for operator, datas in value.items():
                for status, data in datas.items():
                    for i in data:

                        assos_result = i.pop("assos_result", {})
                        format_assos_result = self.format_assos_result(assos_result)
                        if format_assos_result:
                            format_data["association"].extend(format_assos_result)

                        _data = {"_status": status}
                        if status == "failed":
                            update_data = i.get("instance_info")
                        else:
                            update_data = i.get("inst_info")
                        if not update_data:
                            continue
                        _data.update(update_data)
                        format_data[operator].append(_data)

        return format_data

    @staticmethod
    def format_assos_result(assos_result):
        result = []
        for status, data in assos_result.items():
            for i in data:
                i["_status"] = status
                result.append(i)
        return result

    def __call__(self, *args, **kwargs):
        return self.run()
