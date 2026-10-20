# -- coding: utf-8 --
from apps.cmdb.collection.collect_plugin.base import CollectBase, is_failed_vm_metric
from apps.cmdb.collection.collect_util import timestamp_gt_one_day_ago
from apps.cmdb.collection.plugins.base import AutoRegisterCollectionPluginMixin
from apps.cmdb.constants.constants import CollectPluginTypes
from apps.cmdb.models.custom_collect_plugin import CustomCollectPlugin
from apps.cmdb.services.host_sync_identity import parse_cloud_id
from apps.cmdb.services.model import ModelManage

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
        attrs = {attr.get("attr_id"): attr for attr in ModelManage.search_model_attr(task.model_id) or [] if attr.get("attr_id")}
        records = []
        for rows in self.collection_metrics_dict.values():
            for row in rows:
                inst_name = str(row.get("inst_name") or "").strip()
                if not inst_name:
                    self._dropped_records += 1
                    continue
                record = {"inst_name": inst_name}
                for key, raw in row.items():
                    if key in _SYSTEM_LABELS or key not in attrs:
                        continue
                    record[key] = self._convert(attrs[key], raw)
                self._fill_host_cloud(task, attrs, record)
                records.append(record)
        self.result[task.model_id] = records

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
