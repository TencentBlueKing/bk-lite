# -- coding: utf-8 --
from apps.cmdb.collection.collect_plugin.base import CollectBase, is_failed_vm_metric
from apps.cmdb.collection.collect_util import timestamp_gt_one_day_ago
from apps.cmdb.collection.plugins.base import AutoRegisterCollectionPluginMixin
from apps.cmdb.constants.constants import CollectPluginTypes
from apps.cmdb.models.custom_collect_plugin import CustomCollectPlugin
from apps.cmdb.services.host_sync_identity import parse_cloud_id
from apps.cmdb.services.model import ModelManage


def _device_model(row):
    for key in ("model_id", "device_type"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def _existing_device_models(inst_names):
    """按实例名找到已经存在的交换机、路由器、防火墙或负载均衡。"""
    names = [name for name in dict.fromkeys(inst_names) if name]
    if not names:
        return {}
    from apps.cmdb.collection.plugins.community.network.plugins import NETWORK_DEVICE_MODELS
    from apps.cmdb.graph.drivers.graph_client import GraphClient

    with GraphClient() as graph:
        rows = graph.query_entity_by_inst_names(names) or []
    found = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = row.get("inst_name")
        model_id = row.get("model_id")
        if name in found or model_id not in NETWORK_DEVICE_MODELS:
            continue
        found[name] = model_id
    return found


_SYSTEM_LABELS = {
    "__name__",
    "instance_id",
    "model_id",
    "collect_task_id",
    "agent_id",
    "instance_type",
    "collect_type",
    "config_type",
    "job",
    "instance",
}


class CustomScriptCollectionPlugin(AutoRegisterCollectionPluginMixin, CollectBase):
    supported_task_type = CollectPluginTypes.CUSTOM_SCRIPT
    supported_model_id = "*"
    plugin_source = "community"

    def __init__(self, *args, **kwargs):
        self._dropped_records = 0
        self._warnings = []
        super().__init__(*args, **kwargs)

    def _plugin(self):
        task = self.get_collect_inst()
        return CustomCollectPlugin.objects.filter(id=(task.params or {}).get("custom_plugin_pk")).first()

    @property
    def _metrics(self):
        plugin = self._plugin()
        if plugin is None:
            return []
        # VM 按测量名 + gauge 字段落库，序列名是 {plugin_id}_info_gauge。
        # 漏掉 _gauge 时，任务同步查不到已上报的数据。
        return [f"{plugin.plugin_id}_info_gauge"]

    def check_metrics(self):
        return True

    def format_data(self, data):
        for index_data in data.get("result") or []:
            if is_failed_vm_metric(index_data):
                continue
            metric = index_data.get("metric") or {}
            metric_name = metric.get("__name__")
            value = index_data.get("value") or [None, None]
            sample_time = value[0]
            if not self.timestamp_gt and timestamp_gt_one_day_ago(sample_time):
                break
            self.timestamp_gt = True
            bucket = self.collection_metrics_dict.setdefault(metric_name, [])
            bucket.append(dict(metric))

    def format_metrics(self):
        task = self.get_collect_inst()
        if getattr(task, "model_id", None) == "network":
            self._format_network_metrics()
            return
        attrs = {attr.get("attr_id"): attr for attr in ModelManage.search_model_attr(task.model_id) or [] if attr.get("attr_id")}
        records = []
        for rows in self.collection_metrics_dict.values():
            for row in rows:
                record = self._model_record(row, attrs)
                if record is None:
                    continue
                self._fill_host_cloud(task, attrs, record)
                records.append(record)
        self.result[task.model_id] = records

    def _format_network_metrics(self):
        from apps.cmdb.collection.plugins.community.network.plugins import NETWORK_DEVICE_MAPPING, NETWORK_DEVICE_MODELS

        fields = [field for field in NETWORK_DEVICE_MAPPING if field not in {"inst_name", "model_id"}]
        attrs = {field: {"attr_id": field, "attr_type": "str"} for field in fields}
        pending = []
        for rows in self.collection_metrics_dict.values():
            for row in rows:
                record = self._model_record(row, attrs)
                if record is not None:
                    pending.append((row, record))
        unresolved = [record["inst_name"] for row, record in pending if _device_model(row) not in NETWORK_DEVICE_MODELS]
        existing = _existing_device_models(unresolved)
        for row, record in pending:
            model_id = _device_model(row)
            if model_id not in NETWORK_DEVICE_MODELS:
                model_id = existing.get(record["inst_name"], "switch")
            self.result.setdefault(model_id, []).append(record)

    def _model_record(self, row, attrs):
        inst_name = str(row.get("inst_name") or "").strip()
        if not inst_name:
            self._dropped_records += 1
            return None
        record = {"inst_name": inst_name}
        for key, raw in row.items():
            if key in _SYSTEM_LABELS or key not in attrs:
                continue
            record[key] = self._convert(attrs[key], raw)
        return record

    @staticmethod
    def _fill_host_cloud(task, attrs, record):
        """主机唯一键含云区域。脚本没上报时，用任务接入点上的云区域。"""
        if getattr(task, "model_id", None) != "host" or "cloud" not in attrs:
            return
        if parse_cloud_id(record.get("cloud")) is not None:
            return
        access_point = getattr(task, "access_point", None)
        if isinstance(access_point, list):
            access_point = access_point[0] if access_point else None
        params = task.params if isinstance(getattr(task, "params", None), dict) else {}
        sources = [params]
        if isinstance(access_point, dict):
            sources.append(access_point)
        for source in sources:
            for key in ("cloud", "cloud_id", "cloud_region"):
                cloud = parse_cloud_id(source.get(key))
                if cloud is not None:
                    record["cloud"] = cloud
                    return

    def _convert(self, attr, raw):
        attr_type = str(attr.get("attr_type") or "str")
        text = "" if raw is None else str(raw)
        try:
            if attr_type in {"int", "integer"}:
                return int(float(text))
            if attr_type in {"float", "number"}:
                return float(text)
            if attr_type in {"bool", "boolean"}:
                return text.strip().lower() in {"1", "true", "yes"}
            if attr_type == "enum":
                options = {str(item.get("id")) for item in attr.get("option") or [] if isinstance(item, dict)}
                if options and text not in options:
                    self._warnings.append(attr.get("attr_id"))
                    return ""
                return text
        except (TypeError, ValueError):
            self._warnings.append(attr.get("attr_id"))
            return ""
        return text
