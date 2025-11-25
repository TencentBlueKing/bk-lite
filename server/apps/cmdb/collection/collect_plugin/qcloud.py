# -- coding: utf-8 --
# @File: qcloud.py
# @Time: 2025/11/12 14:17
# @Author: windyzhao
from apps.cmdb.collection.collect_plugin.base import CollectBase
from apps.cmdb.collection.collect_util import timestamp_gt_one_day_ago
from apps.cmdb.collection.constants import QCLOUD_COLLECT_CLUSTER


class QCloudCollectMetrics(CollectBase):
    _MODEL_ID = "qcloud"

    def __init__(self, inst_name, inst_id, task_id, *args, **kwargs):
        super().__init__(inst_name, inst_id, task_id, *args, **kwargs)
        self.model_resource_id_mapping = {}

    @property
    def _metrics(self):
        return QCLOUD_COLLECT_CLUSTER

    def prom_sql(self):
        sql = " or ".join(m for m in self._metrics)
        return sql

    @staticmethod
    def set_instance_inst_name(data, *args, **kwargs):
        inst_name = f"{data['resource_name']}_{data['resource_id']}"
        return inst_name

    def set_asso_instances(self, data, *args, **kwargs):
        model_id = kwargs["model_id"]
        result = [
            {
                "model_id": "qcloud",
                "inst_name": self.inst_name,
                "asst_id": "belong",
                "model_asst_id": f"{model_id}_belong_{self._MODEL_ID}"
            }
        ]
        return result

    @property
    def model_field_mapping(self):

        mapping = {
            "qcloud_cvm": {
                "inst_name": self.set_instance_inst_name,
                self.asso: self.set_asso_instances,
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
                "memory_mb": (int, "memory_mb"),
                "charge_type": "charge_type",
            },
            "qcloud_rocketmq": {
                "inst_name": self.set_instance_inst_name,
                self.asso: self.set_asso_instances,
                "resource_name": "resource_name",
                "resource_id": "resource_id",
                "region": "region",
                "zone": "zone",
                "status": "status",
                "topic_num": (int, "topic_num"),
                "used_topic_num": (int, "used_topic_num"),
                "tpsper_name_space": (int, "tpsper_name_space"),
                "name_space_num": (int, "name_space_num"),
                "group_num": (int, "group_num"),
            },
            "qcloud_mysql": {
                "inst_name": self.set_instance_inst_name,
                self.asso: self.set_asso_instances,
                "resource_name": "resource_name",
                "resource_id": "resource_id",
                "ip_addr": "ip_addr",
                "region": "region",
                "zone": "zone",
                "status": "status",
                "volume": (int, "volume"),
                "memory_mb": (int, "memory_mb"),
                "charge_type": "charge_type",
            },
            "qcloud_redis": {
                "inst_name": self.set_instance_inst_name,
                self.asso: self.set_asso_instances,
                "resource_name": "resource_name",
                "resource_id": "resource_id",
                "ip_addr": "ip_addr",
                "vpc": "vpc",
                "region": "region",
                "zone": "zone",
                "port": "port",
                "wan_address": "wan_address",
                "status": "status",
                "sub_status": "sub_status",
                "engine": "engine",
                "version": "version",
                "type": "type",
                "memory_mb": "memory_mb",
                "shard_size": "shard_size",
                "shard_num": "shard_num",
                "replicas_num": "replicas_num",
                "client_limit": "client_limit",
                "net_limit": "net_limit",
                "charge_type": "charge_type",
            },
            "qcloud_mongodb": {
                "inst_name": self.set_instance_inst_name,
                self.asso: self.set_asso_instances,
                "resource_name": "resource_name",
                "resource_id": "resource_id",
                "ip_addr": "ip_addr",
                "tag": "tag",
                "project_id": "project_id",
                "vpc": "vpc",
                "region": "region",
                "zone": "zone",
                "port": "port",
                "status": "status",
                "cluster_type": "cluster_type",
                "machine_type": "machine_type",
                "version": "version",
                "cpu": "cpu",
                "memory_mb": "memory_mb",
                "volume_mb": "volume_mb",
                "secondary_num": "secondary_num",
                "mongos_cpu": "mongos_cpu",
                "mongos_memory_mb": "mongos_memory_mb",
                "mongos_node_num": "mongos_node_num",
                "charge_type": "charge_type",

            },
            "qcloud_pgsql": {
                "inst_name": self.set_instance_inst_name,
                self.asso: self.set_asso_instances,
                "resource_name": "resource_name",
                "resource_id": "resource_id",
                "tag": "tag",
                "project_id": "project_id",
                "vpc": "vpc",
                "region": "region",
                "zone": "zone",
                "status": "status",
                "chartset": "chartset",
                "engine": "engine",
                "mode": "mode",
                "version": "version",
                "kernel_version": "kernel_version",
                "cpu": "cpu",
                "memory_mb": "memory_mb",
                "volume_mb": "volume_mb",
                "charge_type": "charge_type",
            },
            "qcloud_pulsar_cluster": {
                "inst_name": self.set_instance_inst_name,
                self.asso: self.set_asso_instances,
                "resource_name": "resource_name",
                "resource_id": "resource_id",
                "tag": "tag",
                "project_id": "project_id",
                "region": "region",
                "status": "status",
                "version": "version",
                "vpc_endpoint": "vpc_endpoint",
                "public_endpoint": "public_endpoint",
                "max_namespace_num": "max_namespace_num",
                "max_topic_num": "max_topic_num",
                "max_qps": "max_qps",
                "max_retention_s": "max_retention_s",
                "max_storage_mb": "max_storage_mb",
                "max_delay_s": "max_delay_s",
                "charge_type": "charge_type",
            },
            "qcloud_cmq": {
                "inst_name": self.set_instance_inst_name,
                self.asso: self.set_asso_instances,
                "resource_name": "resource_name",
                "resource_id": "resource_id",
                "tag": "tag",
                "region": "region",
                "status": "status",
                "max_delay_s": "max_delay_s",
                "polling_wait_s": "polling_wait_s",
                "visibility_timeout_s": "visibility_timeout_s",
                "max_message_b": "max_message_b",
                "qps": "qps",
            },
            "qcloud_cmq_topic": {
                "inst_name": self.set_instance_inst_name,
                self.asso: self.set_asso_instances,
                "resource_name": "resource_name",
                "resource_id": "resource_id",
                "tag": "tag",
                "region": "region",
                "status": "status",
                "max_retention_s": "max_retention_s",
                "max_message_b": "max_message_b",
                "filter_type": "filter_type",
                "qps": "qps",
            },
            "qcloud_clb": {
                "inst_name": self.set_instance_inst_name,
                self.asso: self.set_asso_instances,
                "resource_name": "resource_name",
                "resource_id": "resource_id",
                "tag": "tag",
                "project_id": "project_id",
                "security_group_id": "security_group_id",
                "vpc": "vpc",
                "region": "region",
                "master_zone": "master_zone",
                "backup_zone": "backup_zone",
                "status": "status",
                "domain": "domain",
                "ip_addr": "ip_addr",
                "type": "type",
                "isp": "isp",
                "charge_type": "charge_type",
            },
            "qcloud_eip": {
                "inst_name": self.set_instance_inst_name,
                self.asso: self.set_asso_instances,
                "resource_name": "resource_name",
                "resource_id": "resource_id",
                "tag": "tag",
                "region": "region",
                "status": "status",
                "type": "type",
                "ip_addr": "ip_addr",
                "instance_type": "instance_type",
                "instance_id": "instance_id",
                "isp": "isp",
                "charge_type": "charge_type",

            },
            "qcloud_bucket": {
                "inst_name": self.set_instance_inst_name,
                self.asso: self.set_asso_instances,
                "resource_name": "resource_name",
                "resource_id": "resource_id",
                "region": "region",
            },
            "qcloud_filesystem": {
                "inst_name": self.set_instance_inst_name,
                self.asso: self.set_asso_instances,
                "resource_name": "resource_name",
                "resource_id": "resource_id",
                "tag": "tag",
                "region": "region",
                "zone": "zone",
                "status": "status",
                "protocol": "protocol",
                "type": "type",
                "net_limit": (int, "net_limit"),
                "size_gib": (int, "size_gib"),
            },
            "qcloud_domain": {
                "inst_name": self.set_instance_inst_name,
                self.asso: self.set_asso_instances,
                "resource_name": "resource_name",
                "resource_id": "resource_id",
                "tld": "tld",
                "status": "status",
            }
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

