# -*- coding: utf-8 -*-
"""ManageOne 采集映射基类：平台→云平台→(云服务器/宿主机/数据存储/ELB) 多层级。

关联键策略：cloud belong 平台(self.inst_name)；子资源 belong 单云回退；
host install_on server 用 host.ip_addr == server.self_host_ip 匹配。
"""
from apps.cmdb.collection.collect_plugin.base import CollectBase
from apps.cmdb.collection.collect_util import timestamp_gt_one_day_ago
from apps.cmdb.collection.plugins import get_collection_plugin
from apps.cmdb.constants.constants import CollectPluginTypes
from apps.core.logger import cmdb_logger as logger


class ManageOneCollectMetrics(CollectBase):
    _MODEL_ID = "manageone"
    # 处理顺序：父在子前
    MODEL_ORDER = [
        "manageone", "manageone_cloud", "manageone_server",
        "manageone_host", "manageone_ds", "manageone_elb",
    ]

    def __init__(self, inst_name, inst_id, task_id, *args, **kwargs):
        super().__init__(inst_name, inst_id, task_id, *args, **kwargs)
        self.single_cloud_inst_name = ""
        self.servers_by_host_ip = {}

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

    # ---- 关联 callables ----
    def asso_cloud(self, data, *args, **kwargs):
        return [{
            "model_id": "manageone",
            "inst_name": self.inst_name,
            "asst_id": "belong",
            "model_asst_id": "manageone_cloud_belong_manageone",
        }]

    def _belong_cloud(self, model_id):
        if not self.single_cloud_inst_name:
            logger.warning(
                "manageone %s 的 belong-cloud 关联未建：云平台非唯一或缺失，多云场景需真机按 region 核对",
                model_id,
            )
            return []
        return [{
            "model_id": "manageone_cloud",
            "inst_name": self.single_cloud_inst_name,
            "asst_id": "belong",
            "model_asst_id": f"{model_id}_belong_manageone_cloud",
        }]

    def asso_server(self, data, *args, **kwargs):
        return self._belong_cloud("manageone_server")

    def asso_host(self, data, *args, **kwargs):
        result = self._belong_cloud("manageone_host")
        host_ip = data.get("ip_addr", "")
        for server_inst in self.servers_by_host_ip.get(host_ip, []):
            result.append({
                "model_id": "manageone_server",
                "inst_name": server_inst,
                "asst_id": "install_on",
                "model_asst_id": "manageone_host_install_on_manageone_server",
            })
        return result

    def asso_ds(self, data, *args, **kwargs):
        return self._belong_cloud("manageone_ds")

    def asso_elb(self, data, *args, **kwargs):
        return self._belong_cloud("manageone_elb")

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
                    logger.warning("skip manageone model=%s due to cmdb_collect_error", model_id)
                    continue
                if model_id != self._MODEL_ID:
                    if not index_data.get("resource_name") or not index_data.get("resource_id"):
                        logger.warning("skip manageone model=%s: incomplete identity", model_id)
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
                            logger.error("manageone convert failed field=%s value=%s err=%s", field, raw, e)
                    elif callable(key_or_func):
                        data[field] = key_or_func(index_data, model_id=model_id)
                    else:
                        data[field] = index_data.get(key_or_func, "")
                if data:
                    result.append(data)
            self.result[model_id] = result
            # 后处理累加器
            if model_id == "manageone_cloud":
                names = [r.get("inst_name") for r in result if r.get("inst_name")]
                self.single_cloud_inst_name = names[0] if len(names) == 1 else ""
            elif model_id == "manageone_server":
                for r in result:
                    ip = r.get("self_host_ip", "")
                    if ip:
                        self.servers_by_host_ip.setdefault(ip, []).append(r.get("inst_name", ""))
