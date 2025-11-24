# -- coding: utf-8 --
# @File: protocol_collect.py
# @Time: 2025/11/12 14:02
# @Author: windyzhao
from apps.cmdb.collection.collect_plugin.base import CollectBase
from apps.cmdb.collection.collect_util import timestamp_gt_one_day_ago
from apps.cmdb.collection.constants import PROTOCOL_METRIC_MAP


class ProtocolCollectMetrics(CollectBase):
    def __init__(self, inst_name, inst_id, task_id, *args, **kwargs):
        super().__init__(inst_name, inst_id, task_id, *args, **kwargs)

    @property
    def _metrics(self):
        data = PROTOCOL_METRIC_MAP[self.model_id]
        return data

    def prom_sql(self):
        sql = " or ".join(m for m in self._metrics)
        return sql

    def get_inst_name(self, data):
        return f"{data['ip_addr']}-{self.model_id}-{data['port']}"

    @property
    def model_field_mapping(self):
        mapping = {
            "mysql": {
                "ip_addr": "ip_addr",
                "port": "port",
                "version": "version",
                "enable_binlog": "enable_binlog",
                "sync_binlog": "sync_binlog",
                "max_conn": "max_conn",
                "max_mem": "max_mem",
                "basedir": "basedir",
                "datadir": "datadir",
                "socket": "socket",
                "bind_address": "bind_address",
                "slow_query_log": "slow_query_log",
                "slow_query_log_file": "slow_query_log_file",
                "log_error": "log_error",
                "wait_timeout": "wait_timeout",
                "inst_name": self.get_inst_name
            },
            "oracle": {
                "version": "version",
                "max_mem": "max_mem",
                "max_conn": "max_conn",
                "db_name": "db_name",
                "database_role": "database_role",
                "sid": "sid",
                "ip_addr": "ip_addr",
                "port": "port",
                "service_name": "service_name",
                "inst_name": lambda data: f"{data['ip_addr']}-oracle",
            },
            "mssql": {
                "inst_name": self.get_inst_name,
                "ip_addr": "ip_addr",
                "port": "port",
                "version": "version",
                "db_name": "db_name",
                "max_conn": "max_conn",
                "max_mem": "max_mem",
                "order_rule": "order_rule",
                "fill_factor": "fill_factor",
                "boot_account": "boot_account",
            },

        }

        return mapping

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

