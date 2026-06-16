# -*- coding: utf-8 -*-
"""华为 OceanStor 存储采集映射基类（多对象，复用云家族机制，对齐 SmartX）。

主对象 storage；子对象 storage_pool / storage_disk / storage_volume。
- 子对象 inst_name 统一拼接所属存储名 `{storage}/{原生名}` 防冲突；
- 容量扇区数 ×SECTORSIZE 归一化为 GB(int)；
- HEALTHSTATUS/RUNNINGSTATUS 数字码归一化到公共库 opera_status；
- 关联：池/磁盘/卷 belong storage；卷 belong 所属池。
"""
from apps.cmdb.collection.collect_plugin.base import CollectBase
from apps.cmdb.collection.collect_util import timestamp_gt_one_day_ago
from apps.cmdb.collection.plugins import get_collection_plugin
from apps.cmdb.constants.constants import CollectPluginTypes
from apps.core.logger import cmdb_logger as logger


class OceanStorCollectMetrics(CollectBase):
    _MODEL_ID = "storage"
    MODEL_ORDER = ["storage", "storage_pool", "storage_disk", "storage_volume"]

    @property
    def _metrics(self):
        plugin_cls = get_collection_plugin(CollectPluginTypes.CLOUD, self.model_id)
        return plugin_cls._metrics.fget(self)

    @property
    def model_field_mapping(self):
        plugin_cls = get_collection_plugin(CollectPluginTypes.CLOUD, self.model_id)
        return plugin_cls.model_field_mapping.fget(self)

    # ------------------------------------------------------------------
    # 归一化 helpers（静态，便于单测）
    # ------------------------------------------------------------------
    @staticmethod
    def to_int(value):
        return int(float(value))

    @staticmethod
    def sectors_to_gb(sectors, sectorsize="512"):
        """扇区数 × 扇区大小(字节) → GB(int)。空值/异常 → 0。"""
        try:
            total_bytes = int(float(sectors)) * int(float(sectorsize))
            return int(total_bytes / (1024 ** 3))
        except (TypeError, ValueError):
            return 0

    # OceanStor RUNNINGSTATUS 常见码 → 公共库 opera_status
    _RUNNING_MAP = {"27": "running", "28": "stopped", "47": "stopped"}

    @staticmethod
    def norm_status(running_code, *args, **kwargs):
        return OceanStorCollectMetrics._RUNNING_MAP.get(str(running_code).strip(), "stopped")

    # ------------------------------------------------------------------
    # field-level callables（实例方法，bind_collection_mapping 绑定 self）
    # ------------------------------------------------------------------
    def self_device(self, data, *args, **kwargs):
        return self.inst_name

    def running_status(self, data, *args, **kwargs):
        return self.norm_status(data.get("RUNNINGSTATUS"))

    def set_child_inst_name(self, data, *args, **kwargs):
        native = data.get("NAME") or data.get("name") or ""
        return f"{self.inst_name}/{native}"

    def set_disk_inst_name(self, data, *args, **kwargs):
        loc = data.get("LOCATION", "")
        model = data.get("MODEL", "")
        return f"{self.inst_name}/{loc}|{model}"

    def pool_total_gb(self, data, *args, **kwargs):
        return self.sectors_to_gb(data.get("USERTOTALCAPACITY"), data.get("SECTORSIZE", "512"))

    def pool_used_gb(self, data, *args, **kwargs):
        return self.sectors_to_gb(data.get("USERCONSUMEDCAPACITY"), data.get("SECTORSIZE", "512"))

    def pool_free_gb(self, data, *args, **kwargs):
        return self.sectors_to_gb(data.get("USERFREECAPACITY"), data.get("SECTORSIZE", "512"))

    def disk_capacity_gb(self, data, *args, **kwargs):
        return self.sectors_to_gb(data.get("SECTORS"), data.get("SECTORSIZE", "512"))

    def volume_capacity_gb(self, data, *args, **kwargs):
        return self.sectors_to_gb(data.get("CAPACITY"), data.get("SECTORSIZE", "512"))

    def volume_alloc_gb(self, data, *args, **kwargs):
        return self.sectors_to_gb(data.get("ALLOCCAPACITY"), data.get("SECTORSIZE", "512"))

    # ------------------------------------------------------------------
    # 关联（子对象 belong storage；卷 belong 所属池）
    # ------------------------------------------------------------------
    def _belong_storage(self, child_model):
        return {
            "model_id": "storage",
            "inst_name": self.inst_name,
            "asst_id": "belong",
            "model_asst_id": f"{child_model}_belong_storage",
        }

    def asso_pool(self, data, *args, **kwargs):
        return [self._belong_storage("storage_pool")]

    def asso_disk(self, data, *args, **kwargs):
        return [self._belong_storage("storage_disk")]

    def asso_volume(self, data, *args, **kwargs):
        out = [self._belong_storage("storage_volume")]
        parent = data.get("PARENTNAME")
        if parent:
            out.append({
                "model_id": "storage_pool",
                "inst_name": f"{self.inst_name}/{parent}",
                "asst_id": "belong",
                "model_asst_id": "storage_volume_belong_storage_pool",
            })
        return out

    # ------------------------------------------------------------------
    # 采集数据处理（对齐 SmartX）
    # ------------------------------------------------------------------
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

    def _child_has_identity(self, model_id, data):
        if model_id == "storage_disk":
            return bool(data.get("LOCATION") or data.get("MODEL"))
        return bool(data.get("NAME") or data.get("name"))

    def format_metrics(self):
        ordered = sorted(self.collection_metrics_dict.items(), key=lambda kv: self._order_index(kv[0]))
        for metric_key, metrics in ordered:
            model_id = metric_key.split("_info_gauge")[0]
            mapping = self.model_field_mapping.get(model_id, {})
            result = []
            for index_data in metrics:
                if index_data.get("cmdb_collect_error"):
                    logger.warning("skip oceanstor model=%s due to cmdb_collect_error", model_id)
                    continue
                if model_id != self._MODEL_ID and not self._child_has_identity(model_id, index_data):
                    logger.warning("skip oceanstor model=%s: incomplete identity", model_id)
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
                            logger.error("oceanstor convert failed field=%s value=%s err=%s", field, raw, e)
                    elif callable(key_or_func):
                        data[field] = key_or_func(index_data, model_id=model_id)
                    else:
                        data[field] = index_data.get(key_or_func, "")
                if data:
                    result.append(data)
            self.result[model_id] = result
