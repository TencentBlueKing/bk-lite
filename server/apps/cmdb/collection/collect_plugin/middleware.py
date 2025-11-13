# -- coding: utf-8 --
# @File: middleware.py
# @Time: 2025/11/12 14:14
# @Author: windyzhao
from apps.cmdb.collection.collect_plugin.base import CollectBase
from apps.cmdb.collection.collect_util import timestamp_gt_one_day_ago
from apps.cmdb.collection.constants import MIDDLEWARE_METRIC_MAP


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

            index_dict = dict(
                index_key=metric_name,
                index_value=value,
                **index_data["metric"],
            )

            self.collection_metrics_dict[metric_name].append(index_dict)

    def get_inst_name(self, data):
        return f"{data['ip_addr']}-{self.model_id}-{data['port']}"

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
                "inst_name":  lambda data: f"{data['ip_addr']}-{self.model_id}-{data['virtual_router_id']}",
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
        }

        return mapping

    def format_metrics(self):
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

    def prom_sql(self):
        sql = " or ".join(m for m in self._metrics)
        return sql
