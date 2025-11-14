# -- coding: utf-8 --
# @File: aws.py
# @Time: 2025/11/12 14:17
# @Author: windyzhao
from apps.cmdb.collection.collect_plugin.base import CollectBase
from apps.cmdb.collection.collect_util import timestamp_gt_one_day_ago
from apps.cmdb.collection.constants import AWS_CLOUD_COLLECT_CLUSTER


class AWSCollectMetrics(CollectBase):
    _MODEL_ID = "aws"

    def __init__(self, inst_name, inst_id, task_id, *args, **kwargs):
        super().__init__(inst_name, inst_id, task_id, *args, **kwargs)
        self.model_resource_id_mapping = {}

    @property
    def _metrics(self):
        return AWS_CLOUD_COLLECT_CLUSTER

    def prom_sql(self):
        sql = " or ".join(m for m in self._metrics)
        return sql

    @property
    def model_field_mapping(self):
        mapping = {
            "aws_ec2": {
                "inst_name": "inst_name",
                "organization": "organization",
                "resource_name": "resource_name",
                "resource_id": "resource_id",
                "ip_addr": "ip_addr",
                "public_ip": "public_ip",
                "region": "region",
                "zone": "zone",
                "vpc": "vpc",
                "status": "status",
                "instance_type": "instance_type",
                "vcpus": "vcpus",
                "key_name": "key_name",
            },
            "aws_rds": {
                "inst_name": "inst_name",
                "organization": "organization",
                "resource_name": "resource_name",
                "resource_id": "resource_id",
                "region": "region",
                "zone": "zone",
                "vpc": "vpc",
                "status": "status",
                "instance_type": "instance_type",
                "engine": "engine",
                "engine_version": "engine_version",
                "parameter_group": "parameter_group",
                "endpoint": "endpoint",
                "maintenance_window": "maintenance_window",
                "ca": "ca",
                "ca_start_date": "ca_start_date",
                "ca_end_date": "ca_end_date",
            },
            "aws_msk": {
                "inst_name": "inst_name",
                "organization": "organization",
                "resource_name": "resource_name",
                "resource_id": "resource_id",
                "region": "region",
                "node_type": "node_type",
                "node_num": "node_num",
                "node_disk": "node_disk",
                "status": "status",
                "cluster_version": "cluster_version",
            },
            "aws_elasticache": {
                "inst_name": "inst_name",
                "organization": "organization",
                "resource_name": "resource_name",
                "resource_id": "resource_id",
                "region": "region",
                "status": "status",
                "engine": "engine",
                "node_type": "node_type",
                "node_num": "node_num",
                "backup_window": "backup_window",
            },
            "aws_eks": {
                "inst_name": "inst_name",
                "organization": "organization",
                "resource_name": "resource_name",
                "resource_id": "resource_id",
                "region": "region",
                "status": "status",
                "k8s_version": "k8s_version",
            },
            "aws_cloudfront": {
                "inst_name": "inst_name",
                "organization": "organization",
                "resource_name": "resource_name",
                "resource_id": "resource_id",
                "status": "status",
                "domain": "domain",
                "aliase_domain": "aliase_domain",
                "modify_time": "modify_time",
                "price_class": "price_class",
                "http_version": "http_version",
                "ssl_method": "ssl_method",
            },
            "aws_elb": {
                "inst_name": "inst_name",
                "organization": "organization",
                "resource_name": "resource_name",
                "resource_id": "resource_id",
                "region": "region",
                "zone": "zone",
                "vpc": "vpc",
                "scheme": "scheme",
                "status": "status",
                "type": "type",
                "dns_name": "dns_name",
            },
            "aws_s3_bucket": {
                "inst_name": "inst_name",
                "organization": "organization",
                "resource_name": "resource_name",
                "resource_id": "resource_id",
                "region": "region",
                "create_date": "create_date",
            },
            "aws_docdb": {
                "inst_name": "inst_name",
                "organization": "organization",
                "resource_name": "resource_name",
                "resource_id": "resource_id",
                "region": "region",
                "status": "status",
                "inst_num": "inst_num",
                "port": "port",
                "engine": "engine",
                "engine_version": "engine_version",
                "parameter_group": "parameter_group",
                "maintenance_window": "maintenance_window",
            },
            "aws_memdb": {
                "inst_name": "inst_name",
                "organization": "organization",
                "resource_name": "resource_name",
                "resource_id": "resource_id",
                "region": "region",
                "node_type": "node_type",
                "shards_num": "shards_num",
                "node_num": "node_num",
                "status": "status",
                "engine_version": "engine_version",
                "parameter_group": "parameter_group",
                "endpoint": "endpoint",
                "maintenance_window": "maintenance_window",
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
