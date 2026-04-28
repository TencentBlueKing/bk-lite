# -- coding: utf-8 --
# @File: middleware.py
# @Time: 2025/11/12 14:14
# @Author: windyzhao
from apps.cmdb.collection.collect_plugin.base import CollectBase
from apps.cmdb.collection.collect_util import timestamp_gt_one_day_ago
from apps.cmdb.collection.plugins import get_collection_plugin
from apps.cmdb.collection.plugins.base import bind_collection_mapping
from apps.cmdb.constants.constants import CollectPluginTypes
import codecs
import json
from apps.core.logger import cmdb_logger as logger

class MiddlewareCollectMetrics(CollectBase):
    @property
    def _metrics(self):
        plugin_cls = get_collection_plugin(CollectPluginTypes.MIDDLEWARE, self.model_id)
        return list(getattr(plugin_cls, "metric_names", ()))

    def format_data(self, data):
        for index_data in data["result"]:
            metric_name = index_data["metric"]["__name__"]
            value = index_data["value"]
            _time, value = value[0], value[1]
            if not self.timestamp_gt:
                if timestamp_gt_one_day_ago(_time):
                    break
                else:
                    self.timestamp_gt = True
            # 原始版本没有result，2025.11.27修改stargazer格式，将采集数据放到result中
            result_data = {}
            if index_data["metric"].get("collect_status", 'failed') == 'failed':
                continue
            if index_data["metric"].get("result", False) or index_data["metric"].get("success", False):
                result_json = index_data["metric"].get("result", "{}")
                if result_json and result_json != "{}":
                    try:
                        unescaped_json = codecs.decode(
                            result_json, 'unicode_escape')
                        result_data = json.loads(unescaped_json)
                    except Exception:  # noqa: BLE001 - JSON解析失败时使用空dict
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

    def get_inst_name(self, data):
        ip_candidate = self.get_ip_addr(data)
        port = ""
        if isinstance(data, dict):
            port = data.get("port") or data.get("listen_port") or ""
        if ip_candidate and port:
            return f"{ip_candidate}-{self.model_id}-{port}"
        if ip_candidate:
            return ip_candidate
        fallback = self._extract_instance_identifier(data)
        if fallback:
            return fallback
        return self.inst_name or ""

    def get_ip_addr(self, data):
        ip_addr = ""
        if isinstance(data, dict):
            ip_addr = data.get("ip_addr") or data.get("host") or data.get("bk_host_innerip")
        if ip_addr:
            return ip_addr
        identifier = self._extract_instance_identifier(data)
        if identifier:
            return identifier
        return self.inst_name or ""

    @staticmethod
    def _extract_instance_identifier(data):
        if not isinstance(data, dict):
            return ""
        instance_id = data.get("instance_id", "")
        if instance_id and "_" in instance_id:
            parts = instance_id.split("_", 1)
            if len(parts) == 2 and parts[1]:
                return parts[1]
        return instance_id or ""

    def get_keepalived_inst_name(self, data):
        ip_addr = self.get_ip_addr(data)
        router_id = ""
        if isinstance(data, dict):
            router_id = data.get("virtual_router_id", "")
        if ip_addr and router_id:
            return f"{ip_addr}-{self.model_id}-{router_id}"
        if router_id:
            return router_id
        return self.get_inst_name(data)


    def get__host_assos(self, data):
        host_inst_name = self.get_ip_addr(data)
        if not host_inst_name:
            logger.warning(
                "实例未解析到主机标识，跳过run关联创建 instance_id=%s node_name=%s",
                data.get("instance_id", "") if isinstance(data, dict) else "",
                data.get("node_name", "") if isinstance(data, dict) else "",
            )
            return []

        return [
            {
                "model_id": "host",
                "inst_name": host_inst_name,
                "asst_id": "run",
                "model_asst_id": "rabbitmq_run_host",
            }
        ]

    @property
    def model_field_mapping(self):
        plugin_cls = get_collection_plugin(CollectPluginTypes.MIDDLEWARE, self.model_id)
        return {self.model_id: bind_collection_mapping(self, getattr(plugin_cls, "field_mapping", {}))}

    @staticmethod
    def extract_nested_value(data, parent_key, child_key, default=""):
        parent = data.get(parent_key) or {}
        if isinstance(parent, dict):
            return parent.get(child_key, default)
        return default

    def get_docker_inst_name(self, data):
        # 若采集结果已经提供 inst_name (容器名)，优先使用
        if data.get("inst_name"):
            return data["inst_name"]
        # 否则退化为 ip-模型名-端口
        return self.get_inst_name(data)

    @staticmethod
    def format_json_field(value):
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        try:
            return json.dumps(value, ensure_ascii=False)
        except Exception:  # noqa: BLE001 - JSON序列化失败时返回空字符串
            return ""

    @staticmethod
    def _extract_primary_port(data):
        if not isinstance(data, dict):
            return ""
        port = data.get("port")
        if port:
            return port
        ports_field = data.get("ports")
        if isinstance(ports_field, list) and ports_field:
            first_port = ports_field[0]
            if isinstance(first_port, dict):
                return first_port.get("host_port") or first_port.get("container_port") or ""
        if isinstance(ports_field, str):
            try:
                parsed = json.loads(ports_field)
                if isinstance(parsed, list) and parsed:
                    first = parsed[0]
                    if isinstance(first, dict):
                        return first.get("host_port") or first.get("container_port") or ""
            except Exception:  # noqa: BLE001 - 端口解析失败时返回空字符串
                return ""
        return ""

    def format_metrics(self):
        for metric_key, metrics in self.collection_metrics_dict.items():
            result = []
            mapping = self.model_field_mapping.get(self.model_id, {})
            for index_data in metrics:
                data = {}
                for field, key_or_func in mapping.items():
                    if isinstance(key_or_func, tuple):
                        try:
                            data[field] = key_or_func[0](index_data[key_or_func[1]])
                        except Exception as e:
                            logger.error(f"数据转换失败 field:{field}, value:{index_data[key_or_func[1]]}, error:{e}")
                    elif callable(key_or_func):
                        try:
                            data[field] = key_or_func(index_data)
                        except Exception as e:
                            logger.error(f"数据处理转换失败 field:{field}, error:{e}")
                    else:
                        data[field] = index_data.get(key_or_func, "")
                if data:
                    result.append(data)
            self.result[self.model_id] = result
