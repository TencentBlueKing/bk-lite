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
        self.server_cpuarch_list = [
            {"name": "x86_64", "id": "x64"},
            {"name": "arm64", "id": "arm64"},
            {"name": "aarch64", "id": "arm64"},
            {"name": "i386", "id": "x86"},
            {"name": "i486", "id": "x86"},
            {"name": "i586", "id": "x86"},
            {"name": "i686", "id": "x86"},
            {"name": "armv7l", "id": "arm"},
            {"name": "armv8l", "id": "arm64"}
        ]
        self.cup_arch_list = [{"id": "x86", "name": "x86"}, {"id": "x64", "name": "x64"}, {"id": "arm", "name": "ARM"},
                              {"id": "arm64", "name": "ARM64"}, {"id": "other", "name": "Other"}]

    @property
    def _metrics(self):
        assert self.model_id in HOST_COLLECT_METRIC, f"{self.model_id} needs to be defined in HOST_COLLECT_METRIC"
        return HOST_COLLECT_METRIC[self.model_id]

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
            "host": {
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
            },
            "physcial_server": {
                "inst_name": self.set_inst_name,
                "serial_number": "serial_number",
                "cpu_vendor": "cpu_vendor",
                "cpu_model": "cpu_model",
                "cpu_core": (self.transform_int, "cpu_cores"),
                "cpu_threads": (self.transform_int, "cpu_threads"),
                "cpu_arch": self.set_serverarch_type,
                "board_vendor": "board_vendor",
                "board_model": "board_model",
                "board_serial": "board_serial",
            },
            "memory": {
                "inst_name": self.set_component_inst_name,
                "self_device":"self_device",
                "mem_locator":"mem_locator",
                "mem_part_number":"mem_part_number",
                "mem_type":"mem_type",
                "mem_size":(self.transform_unit_int, "mem_size"),
                "mem_sn":"mem_sn",
                self.asso: self.set_asso_instances
            },
            "gpu": {
                "inst_name": self.set_component_inst_name,
                "self_device": "self_device",
                "gpu_name": "gpu_name",
                "gpu_type": "gpu_type",
                "gpu_desc": "gpu_desc",
                self.asso: self.set_asso_instances
            },
            "disk": {
                "inst_name": self.set_component_inst_name,
                "self_device": "self_device",
                "disk_vendor": "disk_vendor",
                "disk": (self.transform_unit_int, "disk"),
                "disk_type": "disk_type",
                "disk_sn": "disk_sn",
                self.asso: self.set_asso_instances
            },
            "nic": {
                "inst_name": self.set_component_inst_name,
                "self_device": "self_device",
                "nic_pci_addr": "nic_pci_addr",
                "nic_type": "nic_type",
                "nic_vendor": "nic_vendor",
                "nic_model": "nic_model",
                "nic_iface": "nic_iface",
                "nic_mac": "nic_mac",
                self.asso: self.set_asso_instances
            }
        }
        return mapping

    def set_asso_instances(self, data, *args, **kwargs):
        model_id = kwargs["model_id"]
        result = [
            {
                "model_id": self.model_id,
                "inst_name": data.get('self_device'),
                "asst_id": "contains",
                "model_asst_id": f"{self.model_id}_contains_{model_id}"
            }
        ]
        return result

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

    def set_component_inst_name(self, data, *args, **kwargs):
        """设置实例名称"""
        if self.inst_name:
            return self.inst_name
        result_data = data
        self_device = result_data.get("self_device", "")
        if data['model_id'] == 'nic' and self_device:
            return f"{result_data.get('nic_pci_addr', '')}-{self_device}"
        elif data['model_id'] == 'disk' and self_device:
            return f"{result_data.get('disk_name', '')}-{self_device}"
        elif data['model_id'] == 'memory' and self_device:
            return f"{result_data.get('mem_locator', '')}-{self_device}"
        elif data['model_id'] == 'gpu' and self_device:
            return f"{result_data.get('gpu_name', '')}-{self_device}"
        return ""

    @staticmethod
    def transform_int(data):
        return int(float(data))

    @staticmethod
    def transform_unit_int(data):
        if data is None:
            return 0
        if isinstance(data, (int, float)):
            return int(float(data))
        if isinstance(data, str):
            cleaned = data.replace(",", "")
            match = re.search(r"(\d+(?:\.\d+)?)", cleaned)
            if match:
                return int(float(match.group(1)))
        return 0

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

    def set_serverarch_type(self, data, *args, **kwargs):
        cpu_arch = data.get("cpu_arch", "")
        if not cpu_arch:
            return "other"
        for cpu in self.server_cpuarch_list:
            if cpu["name"].lower() in cpu_arch.lower():
                return cpu["id"]
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
            result_data = {}
            result_json = index_data["metric"].get("result", "{}")
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
            model_id = metric_key.split("_info_gauge")[0]
            mapping = self.model_field_mapping.get(model_id, {})
            result = []
            for index_data in metrics:
                data = {}
                for field, key_or_func in mapping.items():
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
                            data[field] = key_or_func(index_data, model_id=model_id)
                        else:
                            data[field] = index_data.get(key_or_func, "")
                    except (KeyError, ValueError, TypeError):
                        data[field] = 0 if field in [
                            "cpu_core", "memory", "disk"] else ""
                if data:
                    result.append(data)
            self.result[model_id] = result
        # print(json.dumps(self.result, indent=4))

