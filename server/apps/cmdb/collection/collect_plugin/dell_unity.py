# -*- coding: utf-8 -*-
"""Dell Unity 存储采集映射（多对象，复用云家族机制）。

主对象 storage；子对象 storage_pool / storage_disk / storage_volume /
storage_eth_port / storage_fc_port。
- 池/磁盘/卷 inst_name 拼接所属存储名 `{storage}/{原生名}` 防冲突；
- 以太口 / FC 口 inst_name 用归一化 MAC / WWPN（与 nic 同一约定）；
- 容量按字节归一化为 GB(int)；状态字符串归一化到 opera_status；
- 关联：池/磁盘/卷 belong storage；卷 belong 所属池（仅当 parent_pool 存在）；
  口对象写 storage_contains_storage_*_port（storage → 口）。
- 无 MAC / 无 WWPN 跳过，不编造；不写 FDB / interface_connect_*。
"""
from apps.cmdb.collection.collect_plugin.base import CollectBase
from apps.cmdb.collection.collect_util import timestamp_gt_one_day_ago
from apps.cmdb.collection.plugins import get_collection_plugin
from apps.cmdb.collection.storage_port_inventory import normalize_storage_mac, normalize_wwpn, optional_speed, port_display_name
from apps.cmdb.constants.constants import CollectPluginTypes
from apps.core.logger import cmdb_logger as logger

_RUNNING_TOKENS = frozenset({"online", "up", "ok", "healthy", "enabled", "present", "ready", "running", "true"})


class DellUnityCollectMetrics(CollectBase):
    _MODEL_ID = "storage"
    MODEL_ORDER = [
        "storage",
        "storage_pool",
        "storage_disk",
        "storage_volume",
        "storage_eth_port",
        "storage_fc_port",
    ]

    @property
    def _metrics(self):
        plugin_cls = get_collection_plugin(CollectPluginTypes.CLOUD, self.model_id)
        return plugin_cls._metrics.fget(self)

    @property
    def model_field_mapping(self):
        plugin_cls = get_collection_plugin(CollectPluginTypes.CLOUD, self.model_id)
        return plugin_cls.model_field_mapping.fget(self)

    @staticmethod
    def to_int(value):
        return int(float(value))

    @staticmethod
    def bytes_to_gb(value, *args, **kwargs):
        try:
            return int(int(float(value)) / (1024**3))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def norm_status(raw, *args, **kwargs):
        token = str(raw or "").strip().lower()
        if token in _RUNNING_TOKENS or token == "5":
            return "running"
        return "stopped"

    def self_device(self, data, *args, **kwargs):
        return self.inst_name

    def running_status(self, data, *args, **kwargs):
        return self.norm_status(data.get("state") or data.get("isLinkUp") or data.get("health_value"))

    def set_child_inst_name(self, data, *args, **kwargs):
        native = str(data.get("name") or data.get("id") or "").strip().strip("/")
        return f"{self.inst_name}/{native}"

    def set_disk_inst_name(self, data, *args, **kwargs):
        loc = data.get("slotNumber") if data.get("slotNumber") not in (None, "") else data.get("name") or ""
        model = data.get("model") or ""
        return f"{self.inst_name}/{loc}|{model}"

    def pool_total_gb(self, data, *args, **kwargs):
        return self.bytes_to_gb(data.get("sizeTotal"))

    def pool_used_gb(self, data, *args, **kwargs):
        return self.bytes_to_gb(data.get("sizeUsed"))

    def pool_free_gb(self, data, *args, **kwargs):
        return self.bytes_to_gb(data.get("sizeFree"))

    def disk_capacity_gb(self, data, *args, **kwargs):
        return self.bytes_to_gb(data.get("rawSize"))

    def volume_capacity_gb(self, data, *args, **kwargs):
        return self.bytes_to_gb(data.get("sizeTotal"))

    def volume_alloc_gb(self, data, *args, **kwargs):
        return self.bytes_to_gb(data.get("sizeAllocated"))

    def set_eth_mac(self, data, *args, **kwargs):
        return normalize_storage_mac(data.get("macAddress") or data.get("mac"))

    def set_eth_inst_name(self, data, *args, **kwargs):
        return self.set_eth_mac(data)

    def set_port_name(self, data, *args, **kwargs):
        if data.get("name"):
            return port_display_name({"NAME": data.get("name"), "LOCATION": data.get("storageProcessor")})
        return port_display_name(data)

    def set_fc_wwpn(self, data, *args, **kwargs):
        return normalize_wwpn(data.get("wwn") or data.get("wwpn"))

    def set_fc_inst_name(self, data, *args, **kwargs):
        return self.set_fc_wwpn(data)

    def set_fc_speed(self, data, *args, **kwargs):
        return optional_speed({"SPEED": data.get("currentSpeed")})

    def _belong_storage(self, child_model):
        return {
            "model_id": "storage",
            "inst_name": self.inst_name,
            "asst_id": "belong",
            "model_asst_id": f"{child_model}_belong_storage",
        }

    def _contains_storage(self, child_model):
        return {
            "model_id": "storage",
            "inst_name": self.inst_name,
            "asst_id": "contains",
            "model_asst_id": f"storage_contains_{child_model}",
        }

    def asso_pool(self, data, *args, **kwargs):
        return [self._belong_storage("storage_pool")]

    def asso_disk(self, data, *args, **kwargs):
        return [self._belong_storage("storage_disk")]

    def asso_volume(self, data, *args, **kwargs):
        out = [self._belong_storage("storage_volume")]
        parent = data.get("parent_pool")
        if parent:
            out.append(
                {
                    "model_id": "storage_pool",
                    "inst_name": f"{self.inst_name}/{parent}",
                    "asst_id": "belong",
                    "model_asst_id": "storage_volume_belong_storage_pool",
                }
            )
        return out

    def asso_eth_port(self, data, *args, **kwargs):
        return [self._contains_storage("storage_eth_port")]

    def asso_fc_port(self, data, *args, **kwargs):
        return [self._contains_storage("storage_fc_port")]

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
            return bool(data.get("name") or data.get("model") or data.get("id"))
        if model_id == "storage_eth_port":
            return bool(self.set_eth_mac(data))
        if model_id == "storage_fc_port":
            return bool(self.set_fc_wwpn(data))
        return bool(data.get("name") or data.get("id"))

    def format_metrics(self):
        ordered = sorted(self.collection_metrics_dict.items(), key=lambda kv: self._order_index(kv[0]))
        for metric_key, metrics in ordered:
            model_id = metric_key.split("_info_gauge")[0]
            mapping = self.model_field_mapping.get(model_id, {})
            result = []
            for index_data in metrics:
                if index_data.get("cmdb_collect_error"):
                    logger.warning("skip dell_unity model=%s due to cmdb_collect_error", model_id)
                    continue
                if model_id != self._MODEL_ID and not self._child_has_identity(model_id, index_data):
                    logger.warning("skip dell_unity model=%s: incomplete identity", model_id)
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
                            logger.error("dell_unity convert failed field=%s value=%s err=%s", field, raw, e)
                    elif callable(key_or_func):
                        data[field] = key_or_func(index_data, model_id=model_id)
                    else:
                        data[field] = index_data.get(key_or_func, "")
                if data:
                    if model_id == self._MODEL_ID and not data.get("inst_name"):
                        data["inst_name"] = self.inst_name
                    result.append(data)
            self.result[model_id] = result
