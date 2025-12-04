# -- coding: utf-8 --
# @File: vmware.py
# @Time: 2025/11/12 13:49
# @Author: windyzhao
from apps.cmdb.collection.collect_plugin.base import CollectBase
from apps.cmdb.collection.collect_util import timestamp_gt_one_day_ago
from apps.cmdb.collection.constants import VMWARE_CLUSTER, VMWARE_COLLECT_MAP


class CollectVmwareMetrics(CollectBase):
    _MODEL_ID = "vmware_vc"

    def __init__(self, inst_name, inst_id, task_id, *args, **kwargs):
        super().__init__(inst_name, inst_id, task_id, *args, **kwargs)
        self.model_resource_id_mapping = {}

    @property
    def _metrics(self):
        return VMWARE_CLUSTER

    def get_esxi_asso(self, data, *args, **kwargs):
        vmware_ds = data.get("vmware_ds", "")
        vmware_ds_list = vmware_ds.split(",")
        result = [
            {
                "model_id": "vmware_vc",
                "inst_name": self.inst_name,
                "asst_id": "group",
                "model_asst_id": "vmware_esxi_group_vmware_vc",
            }
        ]
        for ds in vmware_ds_list:
            inst_name = self.model_resource_id_mapping["vmware_ds"].get(ds, "")
            result.append({
                "model_id": "vmware_ds",
                "inst_name": inst_name,
                "asst_id": "connect",
                "model_asst_id": "vmware_esxi_connect_vmware_ds"
            })
        return result

    def get_vm_asso(self, data, *args, **kwargs):
        result = []
        esxi_inst_name = self.model_resource_id_mapping["vmware_esxi"].get(data["vmware_esxi"], "")
        if esxi_inst_name:
            result.append({
                "model_id": "vmware_esxi",
                "inst_name": esxi_inst_name,
                "asst_id": "run",
                "model_asst_id": "vmware_vm_run_vmware_esxi"
            })

        vmware_esxi_list = data["vmware_ds"].split(",")
        for ds in vmware_esxi_list:
            inst_name = self.model_resource_id_mapping["vmware_ds"].get(ds, "")
            if not inst_name:
                continue
            result.append({
                "model_id": "vmware_ds",
                "inst_name": inst_name,
                "asst_id": "connect",
                "model_asst_id": "vmware_vm_connect_vmware_ds"
            })
        return result

    @staticmethod
    def set_inst_name(*args, **kwargs):
        """
        {vm的名称}[{moid}]
        """
        data = args[0]
        inst_name = f"{data['inst_name']}[{data['resource_id']}]"
        return inst_name

    @property
    def model_field_mapping(self):
        mapping = {
            "vmware_vc": {
                "vc_version": "vc_version",
                "inst_name": self.inst_name
            },
            "vmware_vm": {
                "inst_name": "inst_name",
                "ip_addr": "ip_addr",
                "resource_id": "resource_id",
                "os_name": "os_name",
                "vcpus": (int, "vcpus"),
                "memory": (int, "memory"),
                self.asso: self.get_vm_asso
            },
            "vmware_esxi": {
                "inst_name": "inst_name",
                "ip_addr": "ip_addr",
                "resource_id": "resource_id",
                "cpu_cores": (int, "cpu_cores"),
                "vcpus": (int, "vcpus"),
                "memory": (int, "memory"),
                "esxi_version": "esxi_version",
                self.asso: self.get_esxi_asso

            },
            "vmware_ds": {
                "inst_name": "inst_name",
                "system_type": "system_type",
                "resource_id": "resource_id",
                "storage": (int, "storage"),
                "url": "url",
                # self.asso: self.get_ds_asso
            }

        }

        return mapping

    def prom_sql(self):
        sql = " or ".join(
            "{}{{instance_id=\"{}\"}}".format(m, f"{self.task_id}_{self.inst_name}") for m in self._metrics)
        return sql

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
            model_id = VMWARE_COLLECT_MAP[metric_key]
            result = []
            if model_id == "vmware_vc":
                self.model_resource_id_mapping.update({model_id: {}})
            else:
                self.model_resource_id_mapping.update({model_id: {i["resource_id"]: i["inst_name"] for i in metrics}})
            mapping = self.model_field_mapping.get(model_id, {})
            for index_data in metrics:
                data = {}
                for field, key_or_func in mapping.items():
                    if isinstance(key_or_func, tuple):
                        data[field] = key_or_func[0](index_data[key_or_func[1]])
                    elif callable(key_or_func):
                        data[field] = key_or_func(index_data, index_data["inst_name"])
                    else:
                        data[field] = index_data.get(key_or_func, "")

                result.append(data)
            self.result[model_id] = result
