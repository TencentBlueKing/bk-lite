# -- coding: utf-8 --
# @File: middleware.py
# @Time: 2025/11/12 14:14
# @Author: windyzhao
from apps.cmdb.collection.collect_plugin.base import CollectBase
from apps.cmdb.collection.collect_util import timestamp_gt_one_day_ago
from apps.cmdb.collection.constants import MIDDLEWARE_METRIC_MAP
import codecs
import json
from apps.core.logger import cmdb_logger as logger

class MiddlewareCollectMetrics(CollectBase):
    @property
    def _metrics(self):
        assert self.model_id in MIDDLEWARE_METRIC_MAP, f"{self.model_id} needs to be defined in MIDDLEWARE_METRIC_MAP"
        return MIDDLEWARE_METRIC_MAP[self.model_id]

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
            if index_data["metric"].get("collect_status", 'success') == 'failed':
                continue
            if index_data["metric"].get("result", False) or index_data["metric"].get("success", False):
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

    @property
    def model_field_mapping(self):
        mapping = {
            "nginx": {
                "ip_addr": "ip_addr",
                # "port": lambda data: data["listen_port"].split("&"), # Multiple ports are separated by &
                "port": "port",
                "bin_path": "bin_path",
                "version": "version",
                "log_path": "log_path",
                "conf_path": "conf_path",
                "server_name": "server_name",
                "include": "include",
                "ssl_version": "ssl_version",
                "inst_name": self.get_inst_name
            },
            "zookeeper": {
                "inst_name": self.get_inst_name,
                "ip_addr": "ip_addr",
                "port": "port",
                "version": "version",
                "install_path": "install_path",  # bin路径
                "log_path": "log_path",  # 运行日志路径
                "conf_path": "conf_path",  # 配置文件路径
                "java_path": "java_path",
                "java_version": "java_version",
                "data_dir": "data_dir",
                "tick_time": "tick_time",
                "init_limit": "init_limit",
                "sync_limit": "sync_limit",
                "server": "server"
            },
            "kafka": {
                "inst_name": self.get_inst_name,
                "ip_addr": "ip_addr",
                "port": "port",
                "version": "version",
                "install_path": "install_path",  # bin路径
                "conf_path": "conf_path",  # 配置文件路径
                "log_path": "log_path",  # 运行日志路径
                "java_path": "java_path",
                "java_version": "java_version",
                "xms": "xms",  # 初始堆内存大小
                "xmx": "xmx",  # 最大堆内存大小
                "broker_id": "broker_id",  # broker id
                "io_threads": "io_threads",
                "network_threads": "network_threads",
                "socket_receive_buffer_bytes": "socket_receive_buffer_bytes",  # 接收缓冲区大小
                "socket_request_max_bytes": "socket_request_max_bytes",  # 单个请求套接字最大字节数
                "socket_send_buffer_bytes": "socket_send_buffer_bytes",  # 发送缓冲区大小
            },
            "etcd": {
                "inst_name": self.get_inst_name,
                "ip_addr": "ip_addr",
                "port": "port",
                "version": "version",
                "data_dir": "data_dir",  # 快照文件路径
                "conf_file_path": "conf_file_path",
                "peer_port": "peer_port",  # 集群通讯端口
                "install_path": "install_path",
            },
            "rabbitmq": {
                "inst_name": self.get_inst_name,
                "ip_addr": "ip_addr",
                "port": "port",
                "allport": "allport",
                "node_name": "node_name",
                "log_path": "log_path",
                "conf_path": "conf_path",
                "version": "version",
                "enabled_plugin_file": "enabled_plugin_file",
                "erlang_version": "erlang_version",
            },
            "tomcat": {
                "inst_name": self.get_inst_name,
                "ip_addr": "ip_addr",
                "port": "port",
                "catalina_path": "catalina_path",
                "version": "version",
                "xms": "xms",
                "xmx": "xmx",
                "max_perm_size": "max_perm_size",
                "permsize": "permsize",
                "log_path": "log_path",
                "java_version": "java_version",
            },
            "apache":{
                "inst_name": self.get_inst_name,
                "ip_addr":"ip_addr",
                "port":"port",
                "version":"version",
                "httpd_path":"httpd_path",
                "httpd_conf_path":"httpd_conf_path",
                "doc_root":"doc_root",
                "error_log":"error_log",
                "custom_Log":"custom_Log",
                "include":"include",
            },
            "consul": {
                "inst_name": self.get_inst_name,
                "ip_addr": "ip_addr",
                "port": "port",
                "install_path": "install_path",
                "version": "version",
                "data_dir": "data_dir",
                "conf_path": "conf_path",
                "role": "role",
            },
            "activemq":{
                "inst_name": self.get_inst_name,
                "ip_addr":"ip_addr",
                "port":"port",
                "version":"version",
                "install_path":"install_path",
                "conf_path":"conf_path",
                "java_path":"java_path",
                "java_version":"java_version",
                "xms":"xms",
                "xmx":"xmx",
            },
            "weblogic": {
                "inst_name": self.get_inst_name,
                "bk_obj_id": "bk_obj_id",
                "ip_addr": "ip_addr",
                "port": "port",
                "wlst_path": "wlst_path",
                "java_version": "java_version",
                "domain_version": "domain_version",
                "admin_server_name": "admin_server_name",
                "name": "name",
            },
            "keepalived": {
                "inst_name": self.get_keepalived_inst_name,
                "ip_addr": "ip_addr",
                "bk_obj_id": "bk_obj_id",
                "version": "version",
                "priority": "priority",
                "state": "state",
                "virtual_router_id": "virtual_router_id",
                "user_name": "user_name",
                "install_path": "install_path",
                "config_file": "config_file",
            },
            "tongweb": {
                "inst_name": self.get_inst_name,
                "ip_addr": "ip_addr",
                "port": "port",
                "version": "version",
                "bin_path": "bin_path",
                "log_path": "log_path",
                "java_version": "java_version",
                "xms": "xms",
                "xmx": "xmx",
                "metaspace_size": "metaspace_size",
                "max_metaspace_size": "max_metaspace_size",
            },
            "jetty": {
                "inst_name": self.get_inst_name,
                "ip_addr": "ip_addr",
                "port": "port",
                "version": "version",
                "jetty_home": "jetty_home",
                "java_version": "java_version",
                "monitored_dir": "monitored_dir",
                "bin_path": "bin_path",
                "java_vendor": "java_vendor",
                "war_name": "war_name",
                "jvm_para": "jvm_para",
                "max_threads": "max_threads",
            },
            "docker": {
                "inst_name": self.get_docker_inst_name,
                "ip_addr": self.get_ip_addr,
                "port": lambda data: data.get("port") or self._extract_primary_port(data),
                "container_id": "container_id",
                "status": "status",
                "command": "command",
                "created": "created",
                "image": "image",
                "networks": lambda data: self.format_json_field(data.get("networks")),
                "ports": "ports",
                "mounts": lambda data: self.format_json_field(data.get("mounts")),
            },
        }

        return mapping

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
        except Exception:
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
            except Exception:
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


