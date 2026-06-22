# -*- coding: utf-8 -*-
"""华为云采集映射基类：查询 hwcloud / hwcloud_ecs 指标并落库到对应模型。

模板对照 collect_plugin/qcloud.py。平台对象 hwcloud 无 resource_id；
子资源 hwcloud_ecs belong hwcloud。
"""
from apps.cmdb.collection.collect_plugin.base import CollectBase
from apps.cmdb.collection.collect_util import timestamp_gt_one_day_ago
from apps.cmdb.collection.plugins import get_collection_plugin
from apps.cmdb.constants.constants import CollectPluginTypes
from apps.core.logger import cmdb_logger as logger


class HwCloudCollectMetrics(CollectBase):
    _MODEL_ID = "hwcloud"
    # 父在子前：ecs 先于 evs(install_on)、vpc 先于 subnet(belong)；其余顺序不敏感。
    MODEL_ORDER = [
        "hwcloud", "hwcloud_ecs", "hwcloud_vpc", "hwcloud_evs", "hwcloud_obs",
        "hwcloud_subnet", "hwcloud_eip", "hwcloud_sg", "hwcloud_elb", "hwcloud_rds", "hwcloud_dcs",
    ]

    def __init__(self, inst_name, inst_id, task_id, *args, **kwargs):
        super().__init__(inst_name, inst_id, task_id, *args, **kwargs)
        self.model_resource_id_mapping = {}
        # 累加器：父对象 resource_id → inst_name，供子对象建关联（隐藏字段命中时）
        self.ecs_by_id = {}
        self.vpc_by_id = {}

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

    def set_asso_instances(self, data, *args, **kwargs):
        model_id = kwargs["model_id"]
        return [
            {
                "model_id": self._MODEL_ID,
                "inst_name": self.inst_name,
                "asst_id": "belong",
                "model_asst_id": f"{model_id}_belong_{self._MODEL_ID}",
            }
        ]

    def asso_evs(self, data, *args, **kwargs):
        """云硬盘：belong 平台 + （隐藏 server_id 命中时）install_on ECS。"""
        result = [{
            "model_id": self._MODEL_ID,
            "inst_name": self.inst_name,
            "asst_id": "belong",
            "model_asst_id": "hwcloud_evs_belong_hwcloud",
        }]
        ecs_inst = self.ecs_by_id.get(data.get("server_id", ""), "")
        if ecs_inst:
            result.append({
                "model_id": "hwcloud_ecs",
                "inst_name": ecs_inst,
                "asst_id": "install_on",
                "model_asst_id": "hwcloud_evs_install_on_hwcloud_ecs",
            })
        return result

    def asso_subnet(self, data, *args, **kwargs):
        """子网：belong 所属 VPC（隐藏 vpc 命中时）；未命中则不建关联并告警。"""
        vpc_inst = self.vpc_by_id.get(data.get("vpc", ""), "")
        if not vpc_inst:
            logger.warning("hwcloud_subnet 关联跳过：未匹配到 VPC(vpc=%s)", data.get("vpc", ""))
            return []
        return [{
            "model_id": "hwcloud_vpc",
            "inst_name": vpc_inst,
            "asst_id": "belong",
            "model_asst_id": "hwcloud_subnet_belong_hwcloud_vpc",
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
            index_dict = dict(
                index_key=metric_name,
                index_value=value,
                **index_data["metric"],
            )
            self.collection_metrics_dict[metric_name].append(index_dict)

    def _order_index(self, metric_key):
        model_id = metric_key.split("_info_gauge")[0]
        return self.MODEL_ORDER.index(model_id) if model_id in self.MODEL_ORDER else 99

    def format_metrics(self):
        ordered = sorted(self.collection_metrics_dict.items(), key=lambda kv: self._order_index(kv[0]))
        for metric_key, metrics in ordered:
            result = []
            model_id = metric_key.split("_info_gauge")[0]
            mapping = self.model_field_mapping.get(model_id, {})
            for index_data in metrics:
                if index_data.get("cmdb_collect_error"):
                    logger.warning("skip hwcloud model=%s due to cmdb_collect_error", model_id)
                    continue
                if model_id != self._MODEL_ID:
                    if not index_data.get("resource_name") or not index_data.get("resource_id"):
                        logger.warning("skip hwcloud model=%s: incomplete identity", model_id)
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
                            logger.error("hwcloud convert failed field=%s value=%s err=%s", field, raw, e)
                    elif callable(key_or_func):
                        data[field] = key_or_func(index_data, model_id=model_id)
                    else:
                        data[field] = index_data.get(key_or_func, "")
                if data:
                    result.append(data)
            self.result[model_id] = result
            # 父对象处理完后建累加器，供后续子对象（evs/subnet）关联解析
            if model_id == "hwcloud_ecs":
                self.ecs_by_id = {r.get("resource_id"): r.get("inst_name") for r in result if r.get("resource_id")}
            elif model_id == "hwcloud_vpc":
                self.vpc_by_id = {r.get("resource_id"): r.get("inst_name") for r in result if r.get("resource_id")}
