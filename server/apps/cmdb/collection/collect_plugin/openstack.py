# -*- coding: utf-8 -*-
"""OpenStack 采集映射基类：平台→节点；卷组关联(节点/虚拟机/存储池)；存储池关联(节点/平台)。

关联键用 stargazer 输出的隐藏字段：vm/sp/vg 带 node_name(匹配 node.resource_name)，
vg 带 vm_id/sp_id(匹配 vm/sp 的 resource_id)。
openstack_vm 不建关联：模型 asso 为自引用疑似笔误，跳过并告警。
"""
from apps.cmdb.collection.collect_plugin.base import CollectBase
from apps.cmdb.collection.collect_util import timestamp_gt_one_day_ago
from apps.cmdb.collection.plugins import get_collection_plugin
from apps.cmdb.constants.constants import CollectPluginTypes
from apps.core.logger import cmdb_logger as logger


class OpenStackCollectMetrics(CollectBase):
    _MODEL_ID = "openstack"
    MODEL_ORDER = ["openstack", "openstack_node", "openstack_vm", "openstack_sp", "openstack_vg"]

    def __init__(self, inst_name, inst_id, task_id, *args, **kwargs):
        super().__init__(inst_name, inst_id, task_id, *args, **kwargs)
        self.node_by_hostname = {}
        self.vm_by_id = {}
        self.sp_by_id = {}

    @property
    def _metrics(self):
        plugin_cls = get_collection_plugin(CollectPluginTypes.CLOUD, self.model_id)
        return plugin_cls._metrics.fget(self)

    @property
    def model_field_mapping(self):
        plugin_cls = get_collection_plugin(CollectPluginTypes.CLOUD, self.model_id)
        return plugin_cls.model_field_mapping.fget(self)

    @staticmethod
    def set_instance_inst_name(data, *args, **kwargs):
        return f"{data['resource_name']}_{data['resource_id']}"

    def asso_node(self, data, *args, **kwargs):
        return [{
            "model_id": "openstack",
            "inst_name": self.inst_name,
            "asst_id": "belong",
            "model_asst_id": "openstack_node_belong_openstack",
        }]

    def asso_vm(self, data, *args, **kwargs):
        logger.warning(
            "openstack_vm 关联跳过：模型 asso-openstack_vm 为自引用(疑似笔误)，"
            "建议模型侧改为 openstack_vm belong openstack_node 后再补关联"
        )
        return []

    def asso_sp(self, data, *args, **kwargs):
        result = [{
            "model_id": "openstack",
            "inst_name": self.inst_name,
            "asst_id": "belong",
            "model_asst_id": "openstack_sp_belong_openstack",
        }]
        node_inst = self.node_by_hostname.get(data.get("node_name", ""), "")
        if node_inst:
            result.append({
                "model_id": "openstack_node",
                "inst_name": node_inst,
                "asst_id": "belong",
                "model_asst_id": "openstack_sp_belong_openstack_node",
            })
        return result

    def asso_vg(self, data, *args, **kwargs):
        result = []
        node_inst = self.node_by_hostname.get(data.get("node_name", ""), "")
        if node_inst:
            result.append({
                "model_id": "openstack_node", "inst_name": node_inst, "asst_id": "belong",
                "model_asst_id": "openstack_vg_belong_openstack_node",
            })
        vm_inst = self.vm_by_id.get(data.get("vm_id", ""), "")
        if vm_inst:
            result.append({
                "model_id": "openstack_vm", "inst_name": vm_inst, "asst_id": "belong",
                "model_asst_id": "openstack_vg_belong_openstack_vm",
            })
        sp_inst = self.sp_by_id.get(data.get("sp_id", ""), "")
        if sp_inst:
            result.append({
                "model_id": "openstack_sp", "inst_name": sp_inst, "asst_id": "belong",
                "model_asst_id": "openstack_vg_belong_openstack_sp",
            })
        return result

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
            if index_data["metric"].get("collect_status", "failed") == "failed":
                continue
            index_dict = dict(index_key=metric_name, index_value=value, **index_data["metric"])
            self.collection_metrics_dict[metric_name].append(index_dict)

    def _order_index(self, metric_key):
        model_id = metric_key.split("_info_gauge")[0]
        return self.MODEL_ORDER.index(model_id) if model_id in self.MODEL_ORDER else 99

    def format_metrics(self):
        ordered = sorted(self.collection_metrics_dict.items(), key=lambda kv: self._order_index(kv[0]))
        for metric_key, metrics in ordered:
            model_id = metric_key.split("_info_gauge")[0]
            mapping = self.model_field_mapping.get(model_id, {})
            result = []
            for index_data in metrics:
                if index_data.get("cmdb_collect_error"):
                    logger.warning("skip openstack model=%s due to cmdb_collect_error", model_id)
                    continue
                if model_id != self._MODEL_ID:
                    if not index_data.get("resource_name") or not index_data.get("resource_id"):
                        logger.warning("skip openstack model=%s: incomplete identity", model_id)
                        continue
                data = {}
                for field, key_or_func in mapping.items():
                    if isinstance(key_or_func, tuple):
                        raw = index_data.get(key_or_func[1])
                        if raw in (None, ""):
                            continue
                        try:
                            data[field] = key_or_func[0](raw)
                        except Exception as e:  # noqa: BLE001
                            logger.error("openstack convert failed field=%s value=%s err=%s", field, raw, e)
                    elif callable(key_or_func):
                        data[field] = key_or_func(index_data, model_id=model_id)
                    else:
                        data[field] = index_data.get(key_or_func, "")
                if data:
                    result.append(data)
            self.result[model_id] = result
            if model_id == "openstack_node":
                self.node_by_hostname = {r.get("resource_name"): r.get("inst_name") for r in result if r.get("resource_name")}
            elif model_id == "openstack_vm":
                self.vm_by_id = {r.get("resource_id"): r.get("inst_name") for r in result if r.get("resource_id")}
            elif model_id == "openstack_sp":
                self.sp_by_id = {r.get("resource_id"): r.get("inst_name") for r in result if r.get("resource_id")}
