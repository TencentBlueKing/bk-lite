# -- coding: utf-8 --
# @File: qcloud.py
# @Time: 2025/11/12 14:17
# @Author: windyzhao
from apps.cmdb.collection.collect_plugin.base import CollectBase
from apps.cmdb.collection.collect_util import timestamp_gt_one_day_ago
from apps.cmdb.collection.plugins import get_collection_plugin
from apps.cmdb.constants.constants import CollectPluginTypes
from apps.core.logger import cmdb_logger as logger


class QCloudCollectMetrics(CollectBase):
    _MODEL_ID = "qcloud"
    MODEL_ID_ALIASES = {
        "qcloud_pulsar_cluster": "qcloud_plusar_cluster",
    }

    def __init__(self, inst_name, inst_id, task_id, *args, **kwargs):
        super().__init__(inst_name, inst_id, task_id, *args, **kwargs)
        self.model_resource_id_mapping = {}

    @property
    def _metrics(self):
        plugin_cls = get_collection_plugin(CollectPluginTypes.CLOUD, self.model_id)
        return plugin_cls._metrics.fget(self)



    @staticmethod
    def set_instance_inst_name(data, *args, **kwargs):
        inst_name = f"{data['resource_name']}_{data['resource_id']}"
        return inst_name

    def set_asso_instances(self, data, *args, **kwargs):
        model_id = kwargs["model_id"]
        result = [
            {
                "model_id": "qcloud",
                "inst_name": self.inst_name,
                "asst_id": "belong",
                "model_asst_id": f"{model_id}_belong_{self._MODEL_ID}"
            }
        ]
        return result

    @property
    def model_field_mapping(self):
        plugin_cls = get_collection_plugin(CollectPluginTypes.CLOUD, self.model_id)
        return plugin_cls.model_field_mapping.fget(self)

    def format_data(self, data):
        """格式化数据"""
        for index_data in data["result"]:
            metric_name = index_data["metric"]["__name__"]
            value = index_data["value"]

            _time, value = value[0], value[1]
            if not self.timestamp_gt:
                if timestamp_gt_one_day_ago(_time):
                    break
                else:
                    self.timestamp_gt = True

            index_dict = dict(
                index_key=metric_name,
                index_value=value,
                **index_data["metric"],
            )

            self.collection_metrics_dict[metric_name].append(index_dict)

    def format_metrics(self):
        """格式化数据"""
        for metric_key, metrics in self.collection_metrics_dict.items():
            result = []
            raw_model_id = metric_key.split("_info_gauge")[0]
            model_id = self.MODEL_ID_ALIASES.get(raw_model_id, raw_model_id)
            mapping = self.model_field_mapping.get(model_id, {})
            for index_data in metrics:
                if index_data.get("cmdb_collect_error"):
                    logger.warning(
                        f"skip qcloud metric formatting for model={model_id} due to cmdb_collect_error="
                        f"{index_data.get('cmdb_collect_error')}"
                    )
                    continue
                if not index_data.get("resource_name") or not index_data.get("resource_id"):
                    logger.warning(
                        f"skip qcloud metric formatting for model={model_id} because resource identity is incomplete: "
                        f"resource_name={index_data.get('resource_name')}, resource_id={index_data.get('resource_id')}"
                    )
                    continue
                data = {}
                for field, key_or_func in mapping.items():
                    if isinstance(key_or_func, tuple):
                        data[field] = key_or_func[0](index_data[key_or_func[1]])
                    elif callable(key_or_func):
                        data[field] = key_or_func(index_data, model_id=model_id)
                    else:
                        data[field] = index_data.get(key_or_func, "")
                if data:
                    result.append(data)
            self.result[model_id] = result
