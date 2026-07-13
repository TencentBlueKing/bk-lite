# -- coding: utf-8 --
# @File: base.py
# @Time: 2025/11/12 14:41
# @Author: windyzhao
from apps.cmdb.collection.metrics_cannula import MetricsCannula
from apps.cmdb.models import CollectModels


class BaseCollect(object):
    COLLECT_PLUGIN = None
    TASK_FORMAT_DATA_KEY = "__task_format_data__"
    RAW_DATA_FIELDS = (
        "id",
        "_id",
        "model_id",
        "inst_name",
        "name",
        "ip_addr",
        "ip",
        "cloud",
        "cloud_id",
        "cloud_name",
        "organization",
        "organization_ids",
        "__time__",
        "_status",
        "_error",
    )

    def __init__(self, instance_id, default_metrics=None, task=None):
        self.task = task or CollectModels.objects.get(id=instance_id)
        self.default_metrics = default_metrics
        self.model_id, self.inst_name, self.organization, self.inst_id, self.filter_collect_task = self.format_params()
        self.plugin_kwargs = self.build_plugin_kwargs()

    def build_plugin_kwargs(self) -> dict:
        """k8s 任务把 collector_cluster_id 透传给采集插件（VM 查询身份与显示名解耦）。"""
        kwargs = {}
        if self.task.is_k8s and self.task.instances:
            instance = self.task.instances[0]
            collector_cluster_id = instance.get("collector_cluster_id") or self.task.params.get("collector_cluster_id")
            if collector_cluster_id:
                kwargs["collector_cluster_id"] = collector_cluster_id
        return kwargs

    def format_params(self):
        if not self.task.instances or not isinstance(self.task.instances, list):
            # IP范围采集模式
            organization = self.task.team
            if not organization:
                organization = self.task.params.get("organization")
                if organization is not None and not isinstance(organization, list):
                    organization = [organization]
            return self.task.model_id, None, organization, None, not self.task.is_host

        instance = self.task.instances[0]
        model_id = instance["model_id"]
        inst_name = instance["inst_name"]
        organization = instance.get("organization") or self.task.team
        if organization is not None and not isinstance(organization, list):
            organization = [organization]
        inst_id = instance["_id"]
        return model_id, inst_name, organization, inst_id, not self.task.is_host

    @property
    def task_id(self):
        # if self.task.is_k8s:
        #     return self.inst_name
        return self.task.id

    def get_collect_plugin(self):
        return self.COLLECT_PLUGIN

    def run(self):
        collect_plugin = self.get_collect_plugin()
        if collect_plugin is None:
            raise NotImplementedError("Please implement the collect plugin")

        metrics_cannula = MetricsCannula(
            inst_id=self.inst_id,
            organization=self.organization,
            inst_name=self.inst_name,
            task_id=self.task_id,
            collect_plugin=collect_plugin,
            manual=bool(self.task.input_method),
            default_metrics=self.default_metrics,
            filter_collect_task=self.filter_collect_task,
            data_cleanup_strategy=self.task.data_cleanup_strategy,
            plugin_kwargs=self.plugin_kwargs,
        )
        result = metrics_cannula.collect_controller()
        format_data = self.format_collect_data(result)
        self.merge_task_format_data(format_data, metrics_cannula.collect_data)
        return metrics_cannula.collect_data, format_data

    def format_collect_data(self, result):
        # 强加了一个原始数据，如果原始数据存在则删除，保留原有逻辑
        raw_data = []
        # 强加一个总数，这个总数是发现正常数据的总数，不是原始数据的总数
        all_count = None
        if result.get("__raw_data__", False) or result.get("__raw_data__", False) == []:
            raw_data = result.pop("__raw_data__")
        if result.get("all", False) or result.get("all", False) == 0:
            all_count = result.pop("all")
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
                            update_data["_error"] = i.get("error", "")
                        else:
                            update_data = i.get("inst_info")
                        if not update_data:
                            continue
                        _data.update(update_data)
                        format_data[operator].append(_data)
        if raw_data:
            format_data["__raw_data__"] = raw_data
        elif all_count:
            # When the collector reports discovered instances but raw VM rows are unavailable,
            # derive a displayable raw_data snapshot from the normalized add/update/delete buckets.
            derived_raw_data = []
            seen = set()
            for operator in ("add", "update", "delete"):
                for item in format_data.get(operator, []):
                    if not isinstance(item, dict):
                        continue
                    identity = (
                        item.get("model_id"),
                        item.get("inst_name"),
                        item.get("ip_addr"),
                        item.get("_id"),
                        item.get("id"),
                    )
                    if identity in seen:
                        continue
                    seen.add(identity)
                    derived_raw_data.append(self._sanitize_raw_data_item(item))
            if derived_raw_data:
                format_data["__raw_data__"] = derived_raw_data
        if all_count is not None:
            format_data["all"] = all_count
        return format_data

    @classmethod
    def _sanitize_raw_data_item(cls, item):
        if not isinstance(item, dict):
            return {}
        sanitized = {key: item.get(key) for key in cls.RAW_DATA_FIELDS if key in item}
        if sanitized.get("model_id") in (None, ""):
            sanitized["model_id"] = "host"
        return sanitized

    @staticmethod
    def format_assos_result(assos_result):
        result = []
        for status, data in assos_result.items():
            for i in data:
                i["_status"] = status
                result.append(i)
        return result

    @classmethod
    def merge_task_format_data(cls, format_data: dict, collect_data: dict) -> dict:
        if not isinstance(format_data, dict) or not isinstance(collect_data, dict):
            return format_data

        extra = collect_data.get(cls.TASK_FORMAT_DATA_KEY)
        if not isinstance(extra, dict):
            return format_data

        for key in ("add", "update", "delete", "association"):
            if extra.get(key):
                format_data.setdefault(key, [])
                format_data[key].extend(extra[key])

        if "all" in extra:
            format_data["all"] = int(format_data.get("all", 0) or 0) + int(extra.get("all", 0) or 0)
        return format_data

    def __call__(self, *args, **kwargs):
        return self.run()
