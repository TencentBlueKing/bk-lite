# -- coding: utf-8 --
from apps.cmdb.collection.collect_plugin.base import CollectBase
from apps.cmdb.collection.collect_util import timestamp_gt_one_day_ago
from apps.cmdb.collection.plugins.base import AutoRegisterCollectionPluginMixin
from apps.cmdb.constants.constants import CollectPluginTypes


class IPAMDiscoveryCollectionPlugin(AutoRegisterCollectionPluginMixin, CollectBase):
    supported_task_type = CollectPluginTypes.IP
    supported_model_id = "ip"
    plugin_source = "community"
    priority = 10
    # Stargazer 会把 ip 模型输出为 ip_info_gauge；保留旧名兼容历史样本/测试数据。
    metric_names = ("ip_info_gauge", "ip_info")
    TASK_FORMAT_DATA_KEY = "__task_format_data__"

    @property
    def _metrics(self):
        return list(self.metric_names)

    def format_data(self, data):
        for index_data in data.get("result", []):
            metric = index_data.get("metric", {})
            if metric.get("__name__") not in self._metrics:
                continue
            value = index_data.get("value", [])
            metric_time = value[0] if value else None
            if metric_time and not self.timestamp_gt:
                if timestamp_gt_one_day_ago(metric_time):
                    break
                self.timestamp_gt = True
            if metric.get("collect_status", "failed") == "failed":
                continue
            self.collection_metrics_dict[metric["__name__"]].append(dict(metric))

    def format_metrics(self):
        from apps.cmdb.services import ipam_discovery

        rows = []
        for metrics in self.collection_metrics_dict.values():
            rows.extend(metrics)
        summary = ipam_discovery.apply_ip_discovery_vm_rows(self.get_collect_inst(), rows)
        self.result[self.model_id] = []
        self.result[self.TASK_FORMAT_DATA_KEY] = summary.get("format_data", {})

    def run(self):
        """IP 发现任务由自定义回写负责落库；这里只向 MetricsCannula 返回空 metrics。

        任务详情所需的 add/update/association 摘要挂在 self.result 的保留键上，
        由 BaseCollect.run 合并进 format_data，不进入通用对比入库流程。
        """
        data = self.query_data()
        self.raw_data = data.get("result", [])
        self.format_data(data)
        self.format_metrics()
        return {self.model_id: []}
