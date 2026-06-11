# -*- coding: utf-8 -*-
"""FusionInsight 采集映射基类：集群 belong 平台(self.inst_name)；主机 belong 集群(隐藏 cluster_id, 单集群回退)。

平台 fusioninsight 无业务字段,不单独采集(=采集任务自身实例),集群直接 belong self.inst_name。
"""
from apps.cmdb.collection.collect_plugin.base import CollectBase
from apps.cmdb.collection.collect_util import timestamp_gt_one_day_ago
from apps.cmdb.collection.plugins import get_collection_plugin
from apps.cmdb.constants.constants import CollectPluginTypes
from apps.core.logger import cmdb_logger as logger


class FusionInsightCollectMetrics(CollectBase):
    _MODEL_ID = "fusioninsight"
    # 顺序关键：cluster 必须先于 host 处理，format_metrics 据此在 cluster 块末
    # 构建 cluster_by_id 累加器，供 host 的 belong-cluster 关联查表。
    MODEL_ORDER = ["fusioninsight_cluster", "fusioninsight_host"]

    def __init__(self, inst_name, inst_id, task_id, *args, **kwargs):
        super().__init__(inst_name, inst_id, task_id, *args, **kwargs)
        self.cluster_by_id = {}
        self.single_cluster_inst_name = ""

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

    def asso_cluster(self, data, *args, **kwargs):
        return [{
            "model_id": "fusioninsight",
            "inst_name": self.inst_name,
            "asst_id": "belong",
            "model_asst_id": "fusioninsight_cluster_belong_fusioninsight",
        }]

    def asso_host(self, data, *args, **kwargs):
        cluster_id = data.get("cluster_id", "")
        cluster_inst = self.cluster_by_id.get(cluster_id, "")
        if not cluster_inst and len(self.cluster_by_id) == 1:
            cluster_inst = next(iter(self.cluster_by_id.values()))
        if not cluster_inst:
            logger.warning("fusioninsight_host 未建 belong-cluster 关联：cluster_id=%s 未匹配且集群非唯一", cluster_id)
            return []
        return [{
            "model_id": "fusioninsight_cluster",
            "inst_name": cluster_inst,
            "asst_id": "belong",
            "model_asst_id": "fusioninsight_host_belong_fusioninsight_cluster",
        }]

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
                    logger.warning("skip fusioninsight model=%s due to cmdb_collect_error", model_id)
                    continue
                if not index_data.get("resource_name") or not index_data.get("resource_id"):
                    logger.warning("skip fusioninsight model=%s: incomplete identity", model_id)
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
                            logger.error("fusioninsight convert failed field=%s value=%s err=%s", field, raw, e)
                    elif callable(key_or_func):
                        data[field] = key_or_func(index_data, model_id=model_id)
                    else:
                        data[field] = index_data.get(key_or_func, "")
                if data:
                    result.append(data)
            self.result[model_id] = result
            if model_id == "fusioninsight_cluster":
                self.cluster_by_id = {r.get("resource_id"): r.get("inst_name") for r in result if r.get("resource_id")}
                self.single_cluster_inst_name = (
                    next(iter(self.cluster_by_id.values())) if len(self.cluster_by_id) == 1 else ""
                )
