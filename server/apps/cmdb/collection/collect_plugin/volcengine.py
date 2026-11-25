# -- coding: utf-8 --
"""火山引擎采集映射。子资源按 resource_id 对账，关系只增不删。"""
from apps.cmdb.collection.collect_plugin.base import CollectBase, is_failed_vm_metric
from apps.cmdb.collection.collect_util import timestamp_gt_one_day_ago
from apps.cmdb.collection.plugins import get_collection_plugin
from apps.cmdb.constants.constants import CollectPluginTypes


class VolcengineCollectMetrics(CollectBase):
    _MODEL_ID = "volcengine_account"
    _ACCOUNT = "volcengine_account"
    _ECS_BIND = "EcsInstance"
    _CLB_BIND = "ClbInstance"

    def __init__(self, inst_name, inst_id, task_id, *args, **kwargs):
        super().__init__(inst_name, inst_id, task_id, *args, **kwargs)

    @property
    def _metrics(self):
        plugin_cls = get_collection_plugin(CollectPluginTypes.CLOUD, self.model_id)
        return plugin_cls._metrics.fget(self)

    def check_task_id(self, instance_id):
        _, task_id = str(instance_id).split("_", 1)
        return task_id == str(self.task_id)

    @staticmethod
    def to_int(value):
        if value in (None, ""):
            return 0
        return int(value)

    @staticmethod
    def set_instance_inst_name(data, *args, **kwargs):
        return f"{data['resource_name']}({data['resource_id']})"

    def set_asso_instances(self, data, *args, **kwargs):
        model_id = kwargs["model_id"]
        relations = [
            {
                "model_id": self._ACCOUNT,
                "inst_name": self.inst_name,
                "asst_id": "belong",
                "model_asst_id": f"{model_id}_belong_{self._ACCOUNT}",
            }
        ]
        if model_id != "volcengine_eip":
            return relations
        bind_type = str(data.get("bind_instance_type") or "")
        bind_id = str(data.get("bind_instance_id") or "")
        target = ""
        if bind_type == self._ECS_BIND:
            target = "volcengine_ecs"
        elif bind_type == self._CLB_BIND:
            target = "volcengine_clb"
        if not target or not bind_id:
            return relations
        peer = ""
        for row in self.result.get(target, []):
            if str(row.get("resource_id") or "") == bind_id:
                peer = row.get("inst_name") or ""
                break
        if not peer:
            return relations
        relations.append(
            {
                "model_id": target,
                "inst_name": peer,
                "asst_id": "connect",
                "model_asst_id": f"volcengine_eip_connect_{target}",
            }
        )
        return relations

    @property
    def model_field_mapping(self):
        plugin_cls = get_collection_plugin(CollectPluginTypes.CLOUD, self.model_id)
        return plugin_cls.model_field_mapping.fget(self)

    def format_data(self, data):
        for index_data in data["result"]:
            metric_name = index_data["metric"]["__name__"]
            value = index_data["value"]
            instance_id = index_data["metric"].get("instance_id", "")
            if not self.check_task_id(instance_id):
                continue
            _time, metric_value = value[0], value[1]
            if not self.timestamp_gt:
                if timestamp_gt_one_day_ago(_time):
                    break
                self.timestamp_gt = True
            self.collection_metrics_dict[metric_name].append(
                dict(
                    index_key=metric_name,
                    index_value=metric_value,
                    **index_data["metric"],
                )
            )

    def format_metrics(self):
        if any(is_failed_vm_metric(row) for row in self.raw_data):
            self.snapshot_complete = False
        for metric_key, metrics in self.collection_metrics_dict.items():
            result = []
            model_id = metric_key.split("_info_gauge")[0]
            mapping = self.model_field_mapping.get(model_id, {})
            for index_data in metrics:
                if str(index_data.get("collect_status", "")).lower() == "failed" or index_data.get("cmdb_collect_error"):
                    continue
                if not index_data.get("resource_name") or not index_data.get("resource_id"):
                    self.snapshot_complete = False
                    continue
                data = {}
                for field, key_or_func in mapping.items():
                    if isinstance(key_or_func, tuple):
                        data[field] = key_or_func[0](index_data.get(key_or_func[1], ""))
                    elif callable(key_or_func):
                        data[field] = key_or_func(index_data, model_id=model_id)
                    else:
                        data[field] = index_data.get(key_or_func, "")
                if data:
                    result.append(data)
            self.result[model_id] = result
