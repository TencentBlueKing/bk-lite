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
    metric_names = ("ip_info",)

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
        ipam_discovery.apply_ip_discovery_vm_rows(self.get_collect_inst(), rows)
        self.result[self.model_id] = []
