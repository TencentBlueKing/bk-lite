# -- coding: utf-8 --
# @File: host.py
# @Time: 2025/11/12 14:06
# @Author: windyzhao
import json
import re
from apps.cmdb.collection.collect_plugin.base import CollectBase
from apps.cmdb.collection.collect_util import timestamp_gt_one_day_ago
from apps.cmdb.collection.plugins import get_collection_plugin
from apps.cmdb.collection.plugins.base import bind_collection_mapping
from apps.cmdb.constants.constants import CollectPluginTypes
from apps.core.logger import cmdb_logger as logger

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
        self.host_proc_map = {}

    @property
    def _metrics(self):
        plugin_cls = get_collection_plugin(CollectPluginTypes.HOST, self.model_id)
        return list(getattr(plugin_cls, "metric_names", ()))

    @property
    def model_field_mapping(self):
        plugin_cls = get_collection_plugin(CollectPluginTypes.HOST, self.model_id)
        mappings = {self.model_id: bind_collection_mapping(self, getattr(plugin_cls, "field_mapping", {}))}
        for model_id, mapping in getattr(plugin_cls, "related_field_mappings", {}).items():
            mappings[model_id] = bind_collection_mapping(self, mapping)
        return mappings

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

    @staticmethod
    def _extract_ip_from_instance_id(instance_id):
        instance_id = str(instance_id or "").strip()
        if instance_id and "_" in instance_id:
            parts = instance_id.split("_", 1)
            if len(parts) == 2:
                return parts[1].strip()
        return ""

    @staticmethod
    def _extract_ip_from_inst_name(inst_name):
        inst_name = str(inst_name or "").strip()
        if not inst_name:
            return ""
        return inst_name.split("[", 1)[0].strip()

    def set_ip_addr(self, data, *args, **kwargs):
        host = str(data.get("host") or "").strip()
        if host:
            return host

        instance_id_ip = self._extract_ip_from_instance_id(data.get("instance_id"))
        if instance_id_ip:
            return instance_id_ip

        inst_name_ip = self._extract_ip_from_inst_name(self.inst_name)
        if inst_name_ip:
            return inst_name_ip

        return host or "unknown"

    def _get_matched_instance_snapshot(self, raw_ip=""):
        task = self.get_collect_inst()
        instances = task.instances if isinstance(task.instances, list) else []

        if raw_ip:
            for instance_item in instances:
                if not isinstance(instance_item, dict):
                    continue
                instance_ip = str(instance_item.get("ip_addr") or instance_item.get("host") or "").strip()
                if not instance_ip:
                    instance_ip = self._extract_ip_from_inst_name(instance_item.get("inst_name"))
                if instance_ip == raw_ip:
                    return instance_item

        return self._get_default_instance_snapshot(instances)

    def set_cloud(self, data, *args, **kwargs):
        raw_ip = self.set_ip_addr(data, *args, **kwargs)
        task = self.get_collect_inst()
        params = task.params if isinstance(task.params, dict) else {}
        matched_instance = self._get_matched_instance_snapshot(raw_ip=raw_ip)
        default_instance = self._get_default_instance_snapshot(task.instances if isinstance(task.instances, list) else [])

        for source in (matched_instance, params, default_instance):
            if not isinstance(source, dict):
                continue
            cloud = source.get("cloud")
            if cloud not in (None, ""):
                return cloud
            cloud_id = source.get("cloud_id")
            if cloud_id not in (None, ""):
                return cloud_id

        return ""

    def _get_cloud_label(self, raw_ip=""):
        task = self.get_collect_inst()
        params = task.params if isinstance(task.params, dict) else {}
        instances = task.instances if isinstance(task.instances, list) else []

        matched_instance = self._get_matched_instance_snapshot(raw_ip=raw_ip)

        for source in (matched_instance, params, self._get_default_instance_snapshot(instances)):
            if not isinstance(source, dict):
                continue
            cloud_name = str(source.get("cloud_name") or "").strip()
            if cloud_name:
                return cloud_name

        for source in (matched_instance, params, self._get_default_instance_snapshot(instances)):
            if not isinstance(source, dict):
                continue
            cloud = str(source.get("cloud") or source.get("cloud_id") or "").strip()
            if cloud:
                return cloud

        return ""

    @staticmethod
    def _get_default_instance_snapshot(instances):
        if isinstance(instances, list) and instances:
            first_instance = instances[0]
            if isinstance(first_instance, dict):
                return first_instance
        return {}

    def set_display_inst_name(self, data, *args, **kwargs):
        raw_ip = self.set_ip_addr(data, *args, **kwargs)
        if not raw_ip or raw_ip == "unknown":
            return self.inst_name or data.get("host", "unknown")

        cloud_label = self._get_cloud_label(raw_ip=raw_ip)
        if cloud_label:
            return f"{raw_ip}[{cloud_label}]"
        return raw_ip

    def set_inst_name(self, data, *args, **kwargs):
        """设置实例名称"""
        if self.inst_name:
            return self.inst_name
        if data.get("host", ""):
            return data["host"]
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

    def get_host_proc(self, data, *args, **kwargs):
        host_key = self.get_host_proc_key(data)
        return json.dumps(self.host_proc_map.get(host_key, []))

    @staticmethod
    def get_host_proc_key(data):
        return data.get("ip_addr") or data.get("host") or data.get("instance_id") or ""

    def add_host_proc(self, data):
        host_key = self.get_host_proc_key(data)
        if not host_key:
            return
        proc_item = {
            "pid": data.get("pid", ""),
            "name": data.get("name", ""),
            "arg": data.get("arg", ""),
            "exe": data.get("exe", ""),
            "cwd": data.get("cwd", ""),
            "ports": data.get("ports", ""),
        }
        self.host_proc_map.setdefault(host_key, []).append(proc_item)

    def format_data(self, data):
        """格式化数据"""
        if not isinstance(data, dict) or "result" not in data:
            return
        for index_data in data.get("result", []):
            metric_name = index_data["metric"]["__name__"]
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
            if index_data["metric"].get("collect_status", 'failed') == 'failed':
                continue
            index_dict = dict(
                index_key=metric_name,
                index_value=value,
                **index_data["metric"],
                **result_data,  # 将解析后的JSON数据合并到index_dict中
            )
            if metric_name == "host_proc_usage_info_gauge":
                self.add_host_proc(index_dict)
                continue
            self.collection_metrics_dict[metric_name].append(index_dict)

    def format_metrics(self):
        """格式化数据"""
        for metric_key, metrics in self.collection_metrics_dict.items():
            model_id = metric_key.split("_info_gauge")[0]
            if not self.model_field_mapping.get(model_id, False):
                continue
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
                            try:
                                data[field] = key_or_func(index_data, model_id=model_id)
                            except Exception as e:
                                logger.error(f"数据处理转换失败 field:{field}, error:{e}")
                        else:
                            data[field] = index_data.get(key_or_func, "")
                    except (KeyError, ValueError, TypeError):
                        data[field] = 0 if field in [
                            "cpu_core", "memory", "disk"] else ""
                if data:
                    result.append(data)
            self.result[model_id] = result
        print(json.dumps(self.result, indent=4))
