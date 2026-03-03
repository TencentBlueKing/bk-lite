from apps.core.logger import celery_logger as logger
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
        try:
            metric = Metric.objects.filter(id=rule["metric_id"]).first()
            if not metric:
                logger.warning(f"规则中的指标不存在，metric_id: {rule.get('metric_id')}")
                return None

            query = metric.query
            # 纬度条件
            vm_filter_str = format_to_vm_filter(rule.get("filter", []))
            vm_filter_str = f"{vm_filter_str}" if vm_filter_str else ""
            # 去掉label尾部多余的逗号
            if vm_filter_str.endswith(","):
                vm_filter_str = vm_filter_str[:-1]
            query = query.replace("__$labels__", vm_filter_str)
            return query
        except Exception as e:
            logger.error(f"构建查询语句失败，metric_id: {rule.get('metric_id')}, 错误: {e}", exc_info=True)
            return None

    @staticmethod
    def get_asso_by_condition_rule(rule):
        """根据条件类型规则获取关联信息"""
        try:
            monitor_objs = MonitorObject.objects.all().values(*MonitorObjConstants.OBJ_KEYS)
            obj_metric_map = {i["name"]: i for i in monitor_objs}
            obj_metric_map = obj_metric_map.get(rule.monitor_object.name)
            obj_instance_id_set = set(MonitorInstance.objects.filter(monitor_object_id=rule.monitor_object_id).values_list("id", flat=True))

            if not obj_metric_map:
                logger.warning(f"规则 {rule.id} 的监控对象 {rule.monitor_object.name} 默认指标不存在")
                return []

            asso_list = []
            # 获取query
            query = RuleGrouping.get_query(rule.rule)
            if not query:
                logger.warning(f"规则 {rule.id} 查询语句构建失败，跳过该规则")
                return []

            metrics = VictoriaMetricsAPI().query(query, step="10m")
            for metric_info in metrics.get("data", {}).get("result", []):
                instance_id = str(tuple([metric_info["metric"].get(i) for i in obj_metric_map["instance_id_keys"]]))
                if instance_id not in obj_instance_id_set:
                    continue
                if instance_id:
                    asso_list.extend([(instance_id, i) for i in rule.organizations])

            return asso_list
        except Exception as e:
            logger.error(f"规则 {rule.id} 处理失败: {e}", exc_info=True)
            return []

    def get_asso_by_select_rule(self, rule):
        """根据选择类型规则获取关联信息"""
        try:
            asso_list = []
            # 过滤掉已经被删除的实例
            obj_instance_id_set = set(MonitorInstance.objects.filter(monitor_object_id=rule.monitor_object_id).values_list("id", flat=True))
            for instance_id in rule.grouping_rules["instances"]:
                if instance_id not in obj_instance_id_set:
                    continue
                asso_list.extend([(instance_id, i) for i in rule.organizations])
            return asso_list
        except Exception as e:
            logger.error(f"选择类型规则 {rule.id} 处理失败: {e}", exc_info=True)
            return []

    def update_grouping(self):
        """更新监控实例分组"""
        monitor_inst_asso_set = set()
        success_count = 0
        failed_count = 0

        logger.info(f"开始更新监控实例分组，共 {len(self.rules)} 条规则")

        for rule in self.rules:
            try:
                asso_list = RuleGrouping.get_asso_by_condition_rule(rule)
                # get_asso_by_condition_rule 返回列表（可能为空）或在内部处理异常后返回空列表
                # 这里直接处理返回的列表即可
                for instance_id, organization in asso_list:
                    monitor_inst_asso_set.add((instance_id, organization))
                success_count += 1
            except Exception as e:
                failed_count += 1
                logger.error(f"规则 {rule.id} 执行失败: {e}", exc_info=True)
                continue

        logger.info(f"规则执行完成 - 成功: {success_count}, 失败: {failed_count}, 生成关联: {len(monitor_inst_asso_set)}")

        try:
            exist_instance_map = {(i.monitor_instance_id, i.organization): i.id for i in MonitorInstanceOrganization.objects.all()}
            create_asso_set = monitor_inst_asso_set - set(exist_instance_map.keys())

            if create_asso_set:
                create_objs = [
                    MonitorInstanceOrganization(monitor_instance_id=asso_tuple[0], organization=asso_tuple[1])
                    for asso_tuple in create_asso_set
                ]
                MonitorInstanceOrganization.objects.bulk_create(create_objs, batch_size=DatabaseConstants.BULK_CREATE_BATCH_SIZE, ignore_conflicts=True)
                logger.info(f"新增监控实例组织关联: {len(create_objs)}")
        except Exception as e:
            logger.error(f"批量创建监控实例组织关联失败: {e}", exc_info=True)
