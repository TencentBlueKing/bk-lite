# -- coding: utf-8 --
# @File: qcloud.py
# @Time: 2025/11/12 14:17
# @Author: windyzhao
from apps.cmdb.collection.collect_plugin.base import CollectBase
from apps.cmdb.collection.collect_util import timestamp_gt_one_day_ago
from apps.cmdb.collection.plugins import get_collection_plugin
from apps.cmdb.constants.constants import CollectPluginTypes
from apps.core.logger import cmdb_logger as logger


class QCloudCollectMetrics(CollectBase):
    _MODEL_ID = "qcloud"
    MODEL_ID_ALIASES = {
        "qcloud_pulsar_cluster": "qcloud_plusar_cluster",
    }
    # 父对象先落库，子对象才能按本轮 inst_name 建边。
    MODEL_ORDER = [
        "qcloud_cvm",
        "qcloud_eip",
        "qcloud_tke_cluster",
        "qcloud_vpn_gateway",
        "qcloud_customer_gateway",
        "qcloud_tke_node",
        "qcloud_vpn_connection",
        "qcloud_nat_gateway",
    ]
    _PARENT_INDEX_ATTR = {
        "qcloud_cvm": "cvm_by_id",
        "qcloud_eip": "eip_by_id",
        "qcloud_tke_cluster": "tke_cluster_by_id",
        "qcloud_vpn_gateway": "vpn_gateway_by_id",
        "qcloud_customer_gateway": "customer_gateway_by_id",
    }

    def __init__(self, inst_name, inst_id, task_id, *args, **kwargs):
        super().__init__(inst_name, inst_id, task_id, *args, **kwargs)
        self.model_resource_id_mapping = {}
        self._reset_peer_indexes()

    @property
    def _metrics(self):
        plugin_cls = get_collection_plugin(CollectPluginTypes.CLOUD, self.model_id)
        return plugin_cls._metrics.fget(self)

    @staticmethod
    def set_instance_inst_name(data, *args, **kwargs):
        inst_name = f"{data['resource_name']}_{data['resource_id']}"
        return inst_name

    @staticmethod
    def set_tke_node_inst_name(data, *args, **kwargs):
        """节点接口没有节点名，用所属集群名区分；旧 Stargazer 不带集群名时沿用通用规则。"""
        cluster_name = str(data.get("cluster_name") or "").strip()
        if not cluster_name:
            return QCloudCollectMetrics.set_instance_inst_name(data)
        return f"{cluster_name}_{data['resource_id']}"

    def set_asso_instances(self, data, *args, **kwargs):
        model_id = kwargs["model_id"]
        return [self._belong_account(model_id)]

    def _reset_peer_indexes(self):
        for attr in self._PARENT_INDEX_ATTR.values():
            setattr(self, attr, {})

    @staticmethod
    def _index_by_resource_id(rows):
        indexed = {}
        for row in rows:
            resource_id = str(row.get("resource_id") or "").strip()
            inst_name = row.get("inst_name") or ""
            if resource_id and inst_name:
                indexed[resource_id] = inst_name
        return indexed

    def _belong_account(self, model_id):
        return {
            "model_id": self._MODEL_ID,
            "inst_name": self.inst_name,
            "asst_id": "belong",
            "model_asst_id": f"{model_id}_belong_{self._MODEL_ID}",
        }

    @staticmethod
    def _peer(src_model, dst_model, inst_name, asst_id):
        return {
            "model_id": dst_model,
            "inst_name": inst_name,
            "asst_id": asst_id,
            "model_asst_id": f"{src_model}_{asst_id}_{dst_model}",
        }

    def set_asso_tke_node(self, data, *args, **kwargs):
        result = [self._belong_account("qcloud_tke_node")]
        cluster_inst = self.tke_cluster_by_id.get(str(data.get("cluster_id") or "").strip())
        if cluster_inst:
            result.append(self._peer("qcloud_tke_node", "qcloud_tke_cluster", cluster_inst, "belong"))
        cvm_inst = self.cvm_by_id.get(str(data.get("resource_id") or "").strip())
        if cvm_inst:
            result.append(self._peer("qcloud_tke_node", "qcloud_cvm", cvm_inst, "connect"))
        return result

    def set_asso_vpn_connection(self, data, *args, **kwargs):
        result = [self._belong_account("qcloud_vpn_connection")]
        gateway_inst = self.vpn_gateway_by_id.get(str(data.get("vpn_gateway_id") or "").strip())
        if gateway_inst:
            result.append(self._peer("qcloud_vpn_connection", "qcloud_vpn_gateway", gateway_inst, "connect"))
        customer_inst = self.customer_gateway_by_id.get(str(data.get("customer_gateway_id") or "").strip())
        if customer_inst:
            result.append(self._peer("qcloud_vpn_connection", "qcloud_customer_gateway", customer_inst, "connect"))
        return result

    def set_asso_nat_gateway(self, data, *args, **kwargs):
        result = [self._belong_account("qcloud_nat_gateway")]
        seen = set()
        for raw in str(data.get("eip_ids") or "").split(","):
            eip_id = raw.strip()
            if not eip_id or eip_id in seen:
                continue
            seen.add(eip_id)
            eip_inst = self.eip_by_id.get(eip_id)
            if eip_inst:
                result.append(self._peer("qcloud_nat_gateway", "qcloud_eip", eip_inst, "connect"))
        return result

    @property
    def model_field_mapping(self):
        plugin_cls = get_collection_plugin(CollectPluginTypes.CLOUD, self.model_id)
        return plugin_cls.model_field_mapping.fget(self)

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

    def _order_index(self, metric_key):
        raw_model_id = metric_key.split("_info_gauge")[0]
        model_id = self.MODEL_ID_ALIASES.get(raw_model_id, raw_model_id)
        try:
            return self.MODEL_ORDER.index(model_id)
        except ValueError:
            return 99

    def format_metrics(self):
        """格式化数据"""
        self._reset_peer_indexes()
        ordered = sorted(self.collection_metrics_dict.items(), key=lambda item: self._order_index(item[0]))
        for metric_key, metrics in ordered:
            result = []
            raw_model_id = metric_key.split("_info_gauge")[0]
            model_id = self.MODEL_ID_ALIASES.get(raw_model_id, raw_model_id)
            mapping = self.model_field_mapping.get(model_id, {})
            for index_data in metrics:
                if index_data.get("cmdb_collect_error"):
                    self.snapshot_complete = False
                    logger.warning(
                        f"skip qcloud metric formatting for model={model_id} due to cmdb_collect_error=" f"{index_data.get('cmdb_collect_error')}"
                    )
                    continue
                if not index_data.get("resource_name") or not index_data.get("resource_id"):
                    self.snapshot_complete = False
                    logger.warning(
                        f"skip qcloud metric formatting for model={model_id} because resource identity is incomplete: "
                        f"resource_name={index_data.get('resource_name')}, resource_id={index_data.get('resource_id')}"
                    )
                    continue
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
            index_attr = self._PARENT_INDEX_ATTR.get(model_id)
            if index_attr:
                setattr(self, index_attr, self._index_by_resource_id(result))
