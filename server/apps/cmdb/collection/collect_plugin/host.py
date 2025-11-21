# -- coding: utf-8 --
# @File: host.py
# @Time: 2025/11/12 14:06
# @Author: windyzhao
import codecs
import json
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
        if self.inst_name:
            # 实例采集模式: 查询特定实例
            sql = " or ".join(
                "{}{{instance_id=\"{}\"}}".format(m, f"{self.task_id}_{self.inst_name}") for m in self._metrics)
        else:
            # IP范围采集模式: 查询任务下所有主机
            sql = " or ".join(
                "{}{{instance_id=~\"^{}_.+\"}}".format(m, self.task_id) for m in self._metrics)
        return sql

    def check_task_id(self, instance_id):
        """检查instance_id是否属于当前采集任务"""
        if "_" not in instance_id:
            return False
        task_id_str = str(self.task_id)

        if self.inst_name:
            return instance_id == f"{task_id_str}_{self.inst_name}"
        else:
            return instance_id.startswith(f"{task_id_str}_")

    @property
    def model_field_mapping(self):
        mapping = {
            "inst_name": self.set_inst_name,
            "ip_addr": self.set_inst_name,
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

    def set_inst_name(self, data, *args, **kwargs):
        """设置实例名称"""
        if self.inst_name:
            return self.inst_name

        # IP范围采集模式: 从instance_id提取IP
        instance_id = data.get("instance_id", "")
        if instance_id and "_" in instance_id:
            parts = instance_id.split("_", 1)
            if len(parts) == 2:
                return parts[1]

        return data.get("host", "unknown")

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
        cpu_arch = data.get("cpu_architecture", "")
        if not cpu_arch:
            return "other"
        for arch in self.cup_arch_list:
            if arch["name"].lower() in cpu_arch.lower():
                return arch["id"]
        return "other"

    def set_os_type(self, data, *args, **kwargs):
        os_type = data.get("os_type", "")
        if not os_type:
            return "other"
        for os in self.os_type_list:
            if os["name"].lower() in os_type.lower():
                return os["id"]
        return "other"

    def format_data(self, data):
        """格式化数据"""
        if not isinstance(data, dict) or "result" not in data:
            return
        for index_data in data.get("result", []):
            metric_name = index_data["metric"]["__name__"]

            # 检查instance_id是否属于当前采集任务
            instance_id = index_data["metric"].get("instance_id", "")
            if instance_id and not self.check_task_id(instance_id):
                continue

            value = index_data["value"]
            _time, value = value[0], value[1]
            if not self.timestamp_gt:
                if timestamp_gt_one_day_ago(_time):
                    break
                else:
                    self.timestamp_gt = True

            # 解析result字段中的JSON数据
            # VictoriaMetrics返回的JSON字符串包含转义字符（如\n），需要先反转义再解析
            result_json = index_data["metric"].get("result", "{}")
            result_data = {}
            if result_json and result_json != "{}":
                try:
                    unescaped_json = codecs.decode(
                        result_json, 'unicode_escape')
                    result_data = json.loads(unescaped_json)
                except Exception:
                    result_data = {}
            if isinstance(result_data, dict) and not result_data:
                continue
            index_dict = dict(
                index_key=metric_name,
                index_value=value,
                **index_data["metric"],
                **result_data,  # 将解析后的JSON数据合并到index_dict中
            )

            self.collection_metrics_dict[metric_name].append(index_dict)

    def format_metrics(self):
        """格式化数据"""
        for metric_key, metrics in self.collection_metrics_dict.items():
            result = []
            for index_data in metrics:
                data = {}
                for field, key_or_func in self.model_field_mapping.items():
                    try:
                        if isinstance(key_or_func, tuple):
                            field_name = key_or_func[1]
                            if field_name in index_data:
                                data[field] = key_or_func[0](
                                    index_data[field_name])
                            else:
                                data[field] = 0 if field in [
                                    "cpu_core", "memory", "disk"] else ""
                        elif callable(key_or_func):
                            data[field] = key_or_func(index_data)
                        else:
                            data[field] = index_data.get(key_or_func, "")
                    except (KeyError, ValueError, TypeError):
                        data[field] = 0 if field in [
                            "cpu_core", "memory", "disk"] else ""
                if data:
                    result.append(data)
            self.result[self.model_id] = result
