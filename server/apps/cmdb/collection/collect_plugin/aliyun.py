# -- coding: utf-8 --
# @File: aliyun.py
# @Time: 2025/11/12 14:02
# @Author: windyzhao
from apps.cmdb.collection.collect_plugin.base import CollectBase
from apps.cmdb.collection.collect_util import timestamp_gt_one_day_ago
from apps.cmdb.collection.constants import ALIYUN_COLLECT_CLUSTER


class AliyunCollectMetrics(CollectBase):
    _MODEL_ID = "aliyun_account"

    def __init__(self, inst_name, inst_id, task_id, *args, **kwargs):
        super().__init__(inst_name, inst_id, task_id, *args, **kwargs)
        self.model_resource_id_mapping = {}

    @property
    def _metrics(self):
        return ALIYUN_COLLECT_CLUSTER

    def prom_sql(self):
        sql = " or ".join(m for m in self._metrics)
        return sql

    def check_task_id(self, instance_id):
        # 只要是同一个account 就认为是同一个task 为了保证不同的区域的数据能在同一个地方采集上来
        # TODO 做下架需要修改逻辑 保证task_id
        task_id, _ = instance_id.split("_", 1)
        return task_id == self.task_id

    @staticmethod
    def set_instance_inst_name(data, *args, **kwargs):
        # {resource_name}（{resource_id}）
        inst_name = f"{data['resource_name']}({data['resource_id']})"
        return inst_name

    def set_asso_instances(self, data, *args, **kwargs):
        model_id = kwargs["model_id"]
        result = [
            {
                "model_id": "aliyun_account",
                "inst_name": self.inst_name,
                "asst_id": "belong",
                "model_asst_id": f"{model_id}_belong_aliyun_account"
            }
        ]
        return result

    @property
    def model_field_mapping(self):
        mapping = {
            "aliyun_ecs": {
                "inst_name": self.set_instance_inst_name,
                "resource_name": "resource_name",
                "resource_id": "resource_id",
                "ip_addr": "ip_addr",
                "public_ip": "public_ip",
                "region": "region",
                "zone": "zone",
                "vpc": "vpc",
                "status": "status",
                "instance_type": "instance_type",
                "os_name": "os_name",
                "vcpus": (int, "vcpus"),
                "memory_mb": (int, "memory"),
                "charge_type": "charge_type",
                "create_time": (self.convert_datetime_format, "create_time"),
                "expired_time": (self.convert_datetime_format, "expired_time"),
                self.asso: self.set_asso_instances
            },
            "aliyun_bucket": {
                "inst_name": self.set_instance_inst_name,
                "resource_name": "resource_name",
                "resource_id": "resource_id",
                "location": "location",
                "extranet_endpoint": "extranet_endpoint",
                "intranet_endpoint": "intranet_endpoint",
                "storage_class": "storage_class",
                "cross_region_replication": "cross_region_replication",
                "block_public_access": "block_public_access",
                "creation_date": (self.convert_datetime_format, "creation_date"),
                self.asso: self.set_asso_instances

            },
            "aliyun_mysql": {
                "inst_name": self.set_instance_inst_name,
                "resource_name": "resource_name",
                "resource_id": "resource_id",
                "region": "region",
                "zone": "zone",
                "zone_slave": "zone_slave",
                "engine": "engine",
                "version": "version",
                "type": "type",
                "status": "status",
                "class": "class",
                "storage_type": "storage_type",
                "network_type": "network_type",
                "net_type": "net_type",
                "connection_mode": "connection_mode",
                "lock_mode": "lock_mode",
                "cpu": (int, "cpu"),
                "memory_mb": (int, "memory_mb"),
                "charge_type": "charge_type",
                "expire_time": (self.convert_datetime_format, "expire_time"),
                self.asso: self.set_asso_instances

            },
            "aliyun_pgsql": {
                "inst_name": self.set_instance_inst_name,
                "resource_name": "resource_name",
                "resource_id": "resource_id",
                "region": "region",
                "zone": "zone",
                "zone_slave": "zone_slave",
                "engine": "engine",
                "version": "version",
                "type": "type",
                "status": "status",
                "class": "class",
                "storage_type": "storage_type",
                "network_type": "network_type",
                "net_type": "net_type",
                "connection_mode": "connection_mode",
                "lock_mode": "lock_mode",
                "cpu": (int, "cpu"),
                "memory_mb": (int, "memory_mb"),
                "charge_type": "charge_type",
                "expire_time": (self.convert_datetime_format, "expire_time"),
                self.asso: self.set_asso_instances

            },
            "aliyun_mongodb": {
                "inst_name": self.set_instance_inst_name,
                "resource_name": "resource_name",
                "resource_id": "resource_id",
                "region": "region",
                "zone": "zone",
                "zone_slave": "zone_slave",
                "engine": "engine",
                "version": "version",
                "type": "type",
                "status": "status",
                "class": "class",
                "storage_type": "storage_type",
                "storage_gb": (int, "storage_gb"),
                "lock_mode": "lock_mode",
                "charge_type": "charge_type",
                "expire_time": (self.convert_datetime_format, "expire_time"),
                self.asso: self.set_asso_instances
            },
            "aliyun_redis": {
                "inst_name": self.set_instance_inst_name,
                "resource_name": "resource_name",
                "resource_id": "resource_id",
                "region": "region",
                "zone": "zone",
                "engine_version": "engine_version",
                "architecture_type": "architecture_type",
                "capacity": "capacity",
                "network_type": "network_type",
                "connection_domain": "connection_domain",
                "port": (int, "port"),
                "bandwidth": (int, "bandwidth"),
                "qps": (int, "qps"),
                "shard_count": "shard_count",
                "instance_class": "instance_class",
                "package_type": "package_type",
                "charge_type": "charge_type",
                "end_time": (self.convert_datetime_format, "end_time"),
                "create_time": (self.convert_datetime_format, "create_time"),
                self.asso: self.set_asso_instances
            },
            "aliyun_clb": {
                "inst_name": self.set_instance_inst_name,
                "resource_name": "resource_name",
                "resource_id": "resource_id",
                "region": "region",
                "zone": "zone",
                "zone_slave": "zone_slave",
                "vpc": "vpc",
                "ip_addr": "ip_addr",
                "status": "status",
                "class": "class",
                "charge_type": "charge_type",
                "create_time": (self.convert_datetime_format, "create_time"),
                self.asso: self.set_asso_instances
            },
            "aliyun_kafka_inst": {
                "inst_name": self.set_instance_inst_name,
                "resource_name": "resource_name",
                "resource_id": "resource_id",
                "region": "region",
                "zone": "zone",
                "vpc": "vpc",
                "status": "status",
                "class": "class",
                "storage_gb": (int, "storage_gb"),
                "storage_type": "storage_type",
                "msg_retain": (int, "msg_retain"),
                "topoc_num": (int, "topoc_num"),
                "io_max_read": (int, "io_max_read"),
                "io_max_write": (int, "io_max_write"),
                "charge_type": "charge_type",
                "create_time": (self.convert_datetime_format, "create_time"),
                self.asso: self.set_asso_instances
            }
        }

        return mapping

    def format_data(self, data):
        """格式化数据"""
        for index_data in data["result"]:
            metric_name = index_data["metric"]["__name__"]
            value = index_data["value"]
            instance_id = index_data["metric"]["instance_id"]
            if not self.check_task_id(instance_id):
                continue

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
            model_id = metric_key.split("_info_gauge")[0]
            mapping = self.model_field_mapping.get(model_id, {})
            for index_data in metrics:
                data = {}
                for field, key_or_func in mapping.items():
                    if isinstance(key_or_func, tuple):
                        data[field] = key_or_func[0](index_data[key_or_func[1]])
                    elif callable(key_or_func):
                        data[field] = key_or_func(index_data, model_id=model_id)
                    else:
                        data[field] = index_data.get(key_or_func, "")
                if data:
                    result.append(data)
            self.result[model_id] = result
