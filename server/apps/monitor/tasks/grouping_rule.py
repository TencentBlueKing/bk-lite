import logging

from celery import shared_task

from apps.monitor.constants import MONITOR_OBJS
from apps.monitor.models.monitor_object import MonitorInstanceGroupingRule, MonitorInstanceOrganization, MonitorObject, \
    MonitorInstance
from apps.monitor.utils.victoriametrics_api import VictoriaMetricsAPI

logger = logging.getLogger("app")


@shared_task
def sync_instance_and_group():
    """同步监控实例和分组规则"""

    logger.info("Start to update monitor instance")
    SyncInstance().run()
    logger.info("Finish to update monitor instance")

    logger.info("Start to update monitor instance grouping rule")
    RuleGrouping().update_grouping()
    logger.info("Finish to update monitor instance grouping rule")


class SyncInstance:

    def __init__(self):
        self.monitor_map = self.get_monitor_map()

    def get_monitor_map(self):
        monitor_objs = MonitorObject.objects.all()
        return {i.name: i.id for i in monitor_objs}

    def get_instance_map_by_metrics(self):
        """通过查询指标获取实例信息"""
        instances_map = {}
        for monitor_info in MONITOR_OBJS:
            if monitor_info["name"] not in self.monitor_map:
                continue
            query = monitor_info["default_metric"]
            metrics = VictoriaMetricsAPI().query(query, step="24h")
            for metric_info in metrics.get("data", {}).get("result", []):
                instance_id = tuple([metric_info["metric"].get(i) for i in monitor_info["instance_id_keys"]])
                instance_name = "__".join([str(i) for i in instance_id])
                if not instance_id:
                    continue
                instance_id = str(instance_id)
                instances_map[instance_id] = {
                    "id": instance_id,
                    "name": instance_name,
                    "monitor_object_id": self.monitor_map[monitor_info["name"]],
                    "auto": True,
                }
        return instances_map

    # 查询库中已有的实例
    def get_exist_instance_set(self):
        exist_instances = MonitorInstance.objects.all()
        return {i.id for i in exist_instances}

    def run(self):
        """更新监控实例"""
        metrics_instance_map = self.get_instance_map_by_metrics()
        exist_instance_set = self.get_exist_instance_set()
        create_instances, delete_instances = [], []
        delete_instances.extend(exist_instance_set - set(metrics_instance_map.keys()))
        for instance_id, instance_info in metrics_instance_map.items():
            if instance_id not in exist_instance_set:
                create_instances.append(MonitorInstance(**instance_info))
        if delete_instances:
            MonitorInstance.objects.filter(id__in=delete_instances, is_deleted=True).delete()
        if create_instances:
            MonitorInstance.objects.bulk_create(create_instances, batch_size=200)

        # todo删除不活跃的实例


class RuleGrouping:
    def __init__(self):
        self.rules = MonitorInstanceGroupingRule.objects.select_related("monitor_object")

    def get_asso_by_condition_rule(self, rule):
        """根据条件类型规则获取关联信息"""
        obj_metric_map = {i["name"]: i for i in MONITOR_OBJS}
        obj_metric_map = obj_metric_map.get(rule.monitor_object.name)
        obj_instance_id_set = set(MonitorInstance.objects.filter(monitor_object_id=rule.monitor_object_id).values_list("id", flat=True))
        if not obj_metric_map:
            raise ValueError("Monitor object default metric does not exist")
        asso_list = []
        metrics = VictoriaMetricsAPI().query(rule.grouping_rules["query"])
        for metric_info in metrics.get("data", {}).get("result", []):
            instance_id = str(tuple([metric_info["metric"].get(i) for i in obj_metric_map["instance_id_keys"]]))
            if instance_id not in obj_instance_id_set:
                continue
            if instance_id:
                asso_list.extend([(instance_id, i) for i in rule.organizations])
        return asso_list

    def get_asso_by_select_rule(self, rule):
        """根据选择类型规则获取关联信息"""
        asso_list = []
        for instance_id in rule.grouping_rules["instances"]:
            asso_list.extend([(instance_id, i) for i in rule.organizations])
        return asso_list


    def update_grouping(self):
        """更新监控实例分组"""
        monitor_inst_asso_set = set()
        for rule in self.rules:
            if rule.type == MonitorInstanceGroupingRule.CONDITION:
                asso_list = self.get_asso_by_condition_rule(rule)
            elif rule.type == MonitorInstanceGroupingRule.SELECT:
                asso_list = self.get_asso_by_select_rule(rule)
            else:
                continue
            for instance_id, organization in asso_list:
                monitor_inst_asso_set.add((instance_id, organization))

        exist_instance_map = {(i.monitor_instance_id, i.organization): i.id for i in MonitorInstanceOrganization.objects.all()}
        create_asso_set = monitor_inst_asso_set - set(exist_instance_map.keys())
        # delete_asso_set = set(exist_instance_map.keys()) - monitor_inst_asso_set

        if create_asso_set:
            create_objs = [
                MonitorInstanceOrganization(monitor_instance_id=asso_tuple[0], organization=asso_tuple[1])
                for asso_tuple in create_asso_set
            ]
            MonitorInstanceOrganization.objects.bulk_create(create_objs, batch_size=200)

        # if delete_asso_set:
        #     delete_ids = [exist_instance_map[asso_tuple] for asso_tuple in delete_asso_set]
        #     MonitorInstanceOrganization.objects.filter(id__in=delete_ids).delete()