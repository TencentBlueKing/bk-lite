# -- coding: utf-8 --
# @File: databases.py
# @Time: 2025/11/12 14:18
# @Author: windyzhao
from apps.cmdb.collection.collect_plugin.base import CollectBase
from apps.cmdb.collection.collect_util import timestamp_gt_one_day_ago
from apps.cmdb.collection.constants import DB_COLLECT_METRIC_MAP


class DBCollectCollectMetrics(CollectBase):
    """数据库 采集指标"""

    @property
    def _metrics(self):
        assert self.model_id in DB_COLLECT_METRIC_MAP, f"{self.model_id} needs to be defined in DB_COLLECT_METRIC_MAP"
        return DB_COLLECT_METRIC_MAP[self.model_id]

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
            "es": {
                "inst_name": self.get_inst_name,
                "ip_addr": "ip_addr",
                "port": "port",
                "version": "version",
                "log_path": "log_path",
                "data_path": "data_path",
                "is_master": "is_master",
                "node_name": "node_name",
                "cluster_name": "cluster_name",
                "java_version": "java_version",
                "java_path": "java_path",
                "conf_path": "conf_path",
                "install_path": "install_path",
            },
            "redis": {
                "inst_name": self.get_inst_name,
                "ip_addr": "ip_addr",
                "port": "port",
                "version": "version",
                "install_path": "install_path",
                "max_conn": "max_conn",
                "max_mem": "max_mem",
                "database_role": "database_role",
            },
            "mongodb": {
                "inst_name": self.get_inst_name,
                "ip_addr": "ip_addr",
                "port": "port",
                "version": "version",
                "mongo_path": "mongo_path",
                "bin_path": "bin_path",
                "config": "config",
                "fork": "fork",
                "system_log": "system_log",
                "db_path": "db_path",
                "max_incoming_conn": "max_incoming_conn",
                "database_role": "database_role",
            },
            "postgresql": {
                "inst_name": lambda x: f"{x['ip_addr']}-pg-{x['port']}",
                "ip_addr": "ip_addr",
                "port": "port",
                "version": "version",
                "conf_path": "conf_path",
                "data_path": "data_path",
                "max_conn": "max_conn",
                "cache_memory_mb": "cache_memory_mb",
                "log_path": "log_path",
            },
            "dameng": {
                "inst_name": self.get_inst_name,
                "ip_addr": "ip_addr",
                "port": "port",
                "user": "user",
                "version": "version",
                "bin_path": "bin_path",
                "dm_db_name": "dm_db_name",
            },
            "db2": {
                "inst_name": lambda data: f"{data['ip_addr']}-db2",
                "version": "version",
                "db_patch": "db_patch",
                "db_name": "db_name",
                "db_instance_name": "db_instance_name",
                "ip_addr": "ip_addr",
                "port": "port",
                "db_character_set": "db_character_set",
                "ha_mode": "ha_mode",
                "replication_managerole": "replication_managerole",
                "replication_role": "replication_role",
                "data_protect_mode": "data_protect_mode",
            },
            "tidb": {
                "inst_name": self.get_inst_name,
                "ip_addr": "ip_addr",
                "port": "port",
                "version": "version",
                "dm_db_name": "dm_db_name",
                "dm_install_path": "dm_install_path",
                "dm_conf_path": "dm_conf_path",
                "dm_log_file": "dm_log_file",
                "dm_home_bash": "dm_home_bash",
                "dm_db_max_sessions": "dm_db_max_sessions",
                "dm_redo_log": "dm_redo_log",
                "dm_datafile": "dm_datafile",
                "dm_mode": "dm_mode",
            },
            "hbase": {
                "inst_name": self.get_inst_name,
                "ip_addr": "ip_addr",
                "port": "port",
                "version": "version",
                "install_path": "install_path",
                "log_path": "log_path",
                "config_file": "config_file",
                "tmp_dir": "tmp_dir",
                "cluster_distributed": "cluster_distributed",
                "unsafe_stream_capability_enforce": "unsafe_stream_capability_enforce",
                "java_path": "java_path",
            }
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
