from apps.cmdb.collection.collect_plugin.base import CollectBase
from apps.cmdb.collection.collect_util import timestamp_gt_one_day_ago
from apps.cmdb.collection.constants import HYPERV_COLLECT_MAP
from apps.cmdb.collection.plugins import get_collection_plugin
from apps.cmdb.constants.constants import CollectPluginTypes
from apps.core.logger import cmdb_logger as logger


class CollectHypervMetrics(CollectBase):
    _MODEL_ID = "hyperv_host"

    def __init__(self, inst_name, inst_id, task_id, *args, **kwargs):
        super().__init__(inst_name, inst_id, task_id, *args, **kwargs)
        self.model_resource_id_mapping = {}

    @property
    def _metrics(self):
        plugin_cls = get_collection_plugin(CollectPluginTypes.VM, self.model_id)
        return plugin_cls._metrics.fget(self)

    @property
    def model_field_mapping(self):
        plugin_cls = get_collection_plugin(CollectPluginTypes.VM, self.model_id)
        return plugin_cls.model_field_mapping.fget(self)

    @staticmethod
    def set_inst_name(*args, **kwargs):
        data = args[0]
        name = data.get("inst_name") or ""
        resource_id = data.get("resource_id") or ""
        if name and resource_id and resource_id not in str(name):
            return f"{name}[{resource_id}]"
        return name

    def set_host_inst_name(self, *args, **kwargs):
        data = args[0]
        return data.get("inst_name") or self.inst_name or data.get("ip_addr") or ""

    def get_vm_asso(self, data, *args, **kwargs):
        host_name = self.model_resource_id_mapping.get("hyperv_host", {}).get(data.get("self_host") or data.get("resource_id"), "")
        if not host_name:
            host_name = data.get("self_host") or ""
        if not host_name:
            return []
        return [
            {
                "model_id": "hyperv_host",
                "inst_name": host_name,
                "asst_id": "run",
                "model_asst_id": "hyperv_vm_run_hyperv_host",
            }
        ]

    def format_data(self, data):
        for index_data in data["result"]:
            metric_name = index_data["metric"]["__name__"]
            if metric_name.endswith("_info"):
                metric_name = f"{metric_name}_gauge"
            if metric_name not in self.collection_metrics_dict:
                continue
            if index_data["metric"].get("collect_status", "failed") == "failed":
                continue
            _time, value = index_data["value"]
            if not self.timestamp_gt:
                if timestamp_gt_one_day_ago(_time):
                    break
                self.timestamp_gt = True
            self.collection_metrics_dict[metric_name].append(dict(index_key=metric_name, index_value=value, **index_data["metric"]))

    def format_metrics(self):
        for metric_key, metrics in self.collection_metrics_dict.items():
            model_id = HYPERV_COLLECT_MAP.get(metric_key)
            if not model_id:
                continue
            mapping = self.model_field_mapping.get(model_id, {})
            result = []
            if model_id == "hyperv_host":
                self.model_resource_id_mapping[model_id] = {
                    item.get("resource_id") or item.get("inst_name"): item.get("inst_name") for item in metrics
                }
            for index_data in metrics:
                row = {}
                for field, key_or_func in mapping.items():
                    if isinstance(key_or_func, tuple):
                        raw_value = index_data.get(key_or_func[1])
                        if raw_value in (None, ""):
                            continue
                        try:
                            row[field] = key_or_func[0](raw_value)
                        except Exception as exc:
                            self.snapshot_complete = False
                            logger.error("Hyper-V field convert failed field=%s value=%s error=%s", field, raw_value, exc)
                    elif callable(key_or_func):
                        try:
                            row[field] = key_or_func(index_data, index_data.get("inst_name", ""))
                        except Exception as exc:
                            self.snapshot_complete = False
                            logger.error("Hyper-V field map failed field=%s error=%s", field, exc)
                    else:
                        value = index_data.get(key_or_func, "")
                        row[field] = value.replace("\\", "") if isinstance(value, str) else value
                result.append(row)
            self.result[model_id] = result
