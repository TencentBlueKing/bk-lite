# -- coding: utf-8 --
# @File: protocol_collect.py
# @Time: 2025/11/12 14:02
# @Author: windyzhao
from apps.cmdb.collection.collect_plugin.base import CollectBase
from apps.cmdb.collection.collect_util import timestamp_gt_one_day_ago
from apps.cmdb.collection.plugins import get_collection_plugin
from apps.cmdb.collection.plugins.base import bind_collection_mapping
from apps.cmdb.constants.constants import CollectPluginTypes
import json
import codecs

class ProtocolCollectMetrics(CollectBase):
    def __init__(self, inst_name, inst_id, task_id, *args, **kwargs):
        super().__init__(inst_name, inst_id, task_id, *args, **kwargs)

    @property
    def _metrics(self):
        plugin_cls = get_collection_plugin(CollectPluginTypes.PROTOCOL, self.model_id)
        return list(getattr(plugin_cls, "metric_names", ()))



    def get_inst_name(self, data):
        return f"{data['ip_addr']}-{self.model_id}-{data['port']}"

    @property
    def model_field_mapping(self):
        plugin_cls = get_collection_plugin(CollectPluginTypes.PROTOCOL, self.model_id)
        return {self.model_id: bind_collection_mapping(self, getattr(plugin_cls, "field_mapping", {}))}

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
            result_data = {}
            if index_data["metric"].get("collect_status", 'failed') == 'failed':
                continue
            index_dict = dict(
                index_key=metric_name,
                index_value=value,
                **index_data["metric"],
                **result_data, # 将解析后的JSON数据合并到index_dict中
            )
            self.collection_metrics_dict[metric_name].append(index_dict)

    def format_metrics(self):
        """格式化数据"""
        for metric_key, metrics in self.collection_metrics_dict.items():
            result = []
            mapping = self.model_field_mapping.get(self.model_id, {})
            for index_data in metrics:
                data = {}
                for field, key_or_func in mapping.items():
                    if isinstance(key_or_func, tuple):
                        data[field] = key_or_func[0](index_data[key_or_func[1]])
                    elif callable(key_or_func):
                        data[field] = key_or_func(index_data)
                    else:
                        data[field] = index_data.get(key_or_func, "")
                if data:
                    result.append(data)
            self.result[self.model_id] = result
