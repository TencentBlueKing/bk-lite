from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.constants.database import DatabaseConstants
from apps.monitor.constants.monitor_object import MonitorObjConstants
from apps.monitor.models import Metric
from apps.monitor.models.monitor_object import MonitorObjectOrganizationRule, MonitorInstanceOrganization, MonitorObject, \
    MonitorInstance
from apps.monitor.tasks.utils.metric_query import format_to_vm_filter
from apps.monitor.utils.victoriametrics_api import VictoriaMetricsAPI


class RuleGrouping:
    def __init__(self):
        self.rules = MonitorObjectOrganizationRule.objects.select_related("monitor_object")

    @staticmethod
    def get_query(rule):
        metric = Metric.objects.filter(id=rule["metric_id"]).first()
        query = metric.query
        # 纬度条件
        vm_filter_str = format_to_vm_filter(rule.get("filter", []))
        vm_filter_str = f"{vm_filter_str}" if vm_filter_str else ""
        # 去掉label尾部多余的逗号
        if vm_filter_str.endswith(","):
            vm_filter_str = vm_filter_str[:-1]
        query = query.replace("__$labels__", vm_filter_str)
        return query

    @staticmethod
    def get_asso_by_condition_rule(rule):
        """根据条件类型规则获取关联信息"""
        monitor_objs = MonitorObject.objects.all().values(*MonitorObjConstants.OBJ_KEYS)
        obj_metric_map = {i["name"]: i for i in monitor_objs}
        obj_metric_map = obj_metric_map.get(rule.monitor_object.name)
        obj_instance_id_set = set(MonitorInstance.objects.filter(monitor_object_id=rule.monitor_object_id).values_list("id", flat=True))
        if not obj_metric_map:
            raise BaseAppException("Monitor object default metric does not exist")
        asso_list = []
        # 获取query
        query = RuleGrouping.get_query(rule.rule)
        metrics = VictoriaMetricsAPI().query(query, step="10m")
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
        # 过滤掉已经被删除的实例
        obj_instance_id_set = set(MonitorInstance.objects.filter(monitor_object_id=rule.monitor_object_id).values_list("id", flat=True))
        for instance_id in rule.grouping_rules["instances"]:
            if instance_id not in obj_instance_id_set:
                continue
            asso_list.extend([(instance_id, i) for i in rule.organizations])
        return asso_list

    def update_grouping(self):
        """更新监控实例分组"""
        monitor_inst_asso_set = set()
        for rule in self.rules:
            # if rule.type == MonitorObjectOrganizationRule.CONDITION:
            #     asso_list = self.get_asso_by_condition_rule(rule)
            # elif rule.type == MonitorObjectOrganizationRule.SELECT:
            #     asso_list = self.get_asso_by_select_rule(rule)
            # else:
            #     continue
            asso_list = RuleGrouping.get_asso_by_condition_rule(rule)
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
            MonitorInstanceOrganization.objects.bulk_create(create_objs, batch_size=DatabaseConstants.BULK_CREATE_BATCH_SIZE, ignore_conflicts=True)

        # if delete_asso_set:
        #     delete_ids = [exist_instance_map[asso_tuple] for asso_tuple in delete_asso_set]
        #     MonitorInstanceOrganization.objects.filter(id__in=delete_ids).delete()