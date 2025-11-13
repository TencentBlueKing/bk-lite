# -- coding: utf-8 --
# @File: host.py
# @Time: 2025/11/12 14:06
# @Author: windyzhao
import re

from apps.cmdb.collection.collect_plugin.base import CollectBase
from apps.cmdb.collection.collect_util import timestamp_gt_one_day_ago
from apps.cmdb.collection.constants import HOST_COLLECT_METRIC


class HostCollectMetrics(CollectBase):
    def __init__(self, inst_name, inst_id, task_id, *args, **kwargs):
        super().__init__(inst_name, inst_id, task_id, *args, **kwargs)
        self.os_type_list = [{"id": "1", "name": "Linux"}, {"id": "2", "name": "Windows"},
                             {"id": "3", "name": "AIX"},
                             {"id": "4", "name": "Unix"}, {"id": "other", "name": "Other"}]
        self.cup_arch_list = [{"id": "x86", "name": "x86"}, {"id": "x64", "name": "x64"}, {"id": "arm", "name": "ARM"},
                              {"id": "arm64", "name": "ARM64"}, {"id": "other", "name": "Other"}]

    @property
    def _metrics(self):
        metrics = HOST_COLLECT_METRIC
        return metrics

    def prom_sql(self):
        sql = " or ".join(
            "{}{{instance_id=\"{}\"}}".format(m, f"{self.task_id}_{self.inst_name}") for m in self._metrics)
        return sql

    @property
    def model_field_mapping(self):
        mapping = {
            "inst_name": self.set_inst_name,
            "hostname": "hostname",
            "os_type": self.set_os_type,
            "os_name": "os_name",
            "os_version": "os_version",
            "os_bit": "os_bits",
            "cpu_model": "cpu_model",
            "cpu_core": (self.transform_int, "cpu_cores"),
            "memory": (self.transform_int, "memory_gb"),
            "disk": (self.transform_int, "disk_gb"),
            "cpu_arch": self.set_cpu_arch,
            "inner_mac": (self.format_mac, "mac_address"),

        }

        return mapping

    def set_inst_name(self, *args, **kwargs):
        return self.inst_name

    @staticmethod
    def transform_int(data):
        return int(float(data))

    @staticmethod
    def format_mac(mac, *args, **kwargs):
        # 统一转为大写，冒号分隔
        mac = mac.strip().lower().replace("-", ":")
        if not re.match(r"^([0-9a-f]{2}:){5}[0-9a-f]{2}$", mac):
            return mac
        return mac.upper()

    def set_cpu_arch(self, data, *args, **kwargs):
        cpu_arch = data["cpu_architecture"]
        for arch in self.cup_arch_list:
            if arch["name"].lower() in cpu_arch.lower():
                return arch["id"]
        return "other"

    def set_os_type(self, data, *args, **kwargs):
        os_type = data["os_type"]
        for os in self.os_type_list:
            if os["name"].lower() in os_type.lower():
                return os["id"]
        return "other"

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
            for index_data in metrics:
                data = {}
                for field, key_or_func in self.model_field_mapping.items():
                    if isinstance(key_or_func, tuple):
                        data[field] = key_or_func[0](index_data[key_or_func[1]])
                    elif callable(key_or_func):
                        data[field] = key_or_func(index_data)
                    else:
                        data[field] = index_data.get(key_or_func, "")
                if data:
                    result.append(data)
            self.result[self.model_id] = result
