import ast

from django.db import transaction

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import monitor_logger as logger
from apps.monitor.constants.database import DatabaseConstants
from apps.monitor.models import MonitorInstance, MonitorInstanceOrganization, CollectConfig, MonitorObject, \
    MonitorObjectOrganizationRule, Metric
from apps.monitor.utils.config_format import ConfigFormat
from apps.monitor.utils.instance import calculation_status
from apps.monitor.utils.plugin_controller import Controller
from apps.monitor.utils.victoriametrics_api import VictoriaMetricsAPI
from apps.rpc.node_mgmt import NodeMgmt


class InstanceConfigService:
    @staticmethod
    def get_instance_configs(collect_instance_id, instance_type):
        """获取实例配置"""
        # 获取实例配置
        _collect_instance_id = ast.literal_eval(collect_instance_id)[0]
        pmq = f'any({{instance_id="{_collect_instance_id}", instance_type="{instance_type}"}}) by (instance_id, collect_type, config_type)'

        metrics = VictoriaMetricsAPI().query(pmq, "10m")
        instance_config_map = {}
        for metric_info in metrics.get("data", {}).get("result", []):
            instance_id = metric_info.get("metric", {}).get("instance_id")
            if not instance_id:
                continue
            instance_id = str(tuple([instance_id]))
            agent_id = metric_info.get("metric", {}).get("agent_id")
            collect_type = metric_info.get("metric", {}).get("collect_type")
            config_type = metric_info.get("metric", {}).get("config_type")
            _time = metric_info["value"][0]
            config_info = {
                "agent_id": agent_id,
                "time": _time,
            }
            if config_info["time"] == 0:
                config_info["status"] = ""
            else:
                config_info["status"] = calculation_status(config_info["time"])
            instance_config_map[(instance_id, collect_type, config_type)] = config_info

        config_objs = CollectConfig.objects.filter(monitor_instance_id=collect_instance_id)

        configs = []

        for config_obj in config_objs:
            config_info = instance_config_map.get(
                (config_obj.monitor_instance_id, config_obj.collect_type, config_obj.config_type), {}
            )
            configs.append({
                "config_id": config_obj.id,
                "collector": config_obj.collector,
                "collect_type": config_obj.collect_type,
                "config_type": config_obj.config_type,
                "instance_id": collect_instance_id,
                "is_child": config_obj.is_child,
                "agent_id": config_info.get("agent_id"),
                "time": config_info.get("time"),
                "status": config_info.get("status"),
            })

        result = {}
        for config in configs:
            key = (config["collect_type"], config["config_type"])
            if key not in result:
                result[key] = {
                    "instance_id": config["instance_id"],
                    "collect_type": config["collect_type"],
                    "config_type": config["config_type"],
                    "agent_id": config["agent_id"],
                    "time": config["time"],
                    "status": config["status"],
                    "config_ids": [config["config_id"]],
                }
            else:
                result[key]["config_ids"].append(config["config_id"])

        return list(result.values())

    @staticmethod
    def create_default_rule(monitor_object_id, monitor_instance_id, group_ids):
        """存在子模型的要给子模型默认规则

        返回创建的规则ID列表，用于失败时回滚
        """
        child_objs = MonitorObject.objects.filter(parent_id=monitor_object_id)
        if not child_objs:
            return []

        rules = []
        _monitor_instance_id = ast.literal_eval(monitor_instance_id)[0]

        for child_obj in child_objs:
            metric_obj = Metric.objects.filter(monitor_object_id=child_obj.id).first()
            if not metric_obj:
                logger.warning(f"子对象 {child_obj.id} 没有关联指标，跳过规则创建")
                continue

            rules.append(MonitorObjectOrganizationRule(
                name=f"{child_obj.name}-{monitor_instance_id}",
                monitor_object_id=child_obj.id,
                rule={
                    "type": "metric",
                    "metric_id": metric_obj.id,
                    "filter": [{"name": "instance_id", "method": "=", "value": _monitor_instance_id}]
                },
                organizations=group_ids,
                monitor_instance_id=monitor_instance_id,
            ))

        if rules:
            created_rules = MonitorObjectOrganizationRule.objects.bulk_create(
                rules,
                batch_size=DatabaseConstants.BULK_CREATE_BATCH_SIZE
            )
            return [rule.id for rule in created_rules]

        return []

    @staticmethod
    def _prepare_instances_for_creation(instances):
        """准备待创建实例:格式化ID、检查冲突、过滤有效实例

        Returns:
            tuple: (new_instances, deleted_ids) 或抛出异常
        """
        # 格式化实例ID
        for instance in instances:
            instance["instance_id"] = str(tuple([instance["instance_id"]]))

        # 检查已存在的实例
        instance_ids = [inst["instance_id"] for inst in instances]
        existing_instances = MonitorInstance.objects.filter(
            id__in=instance_ids
        ).values_list('id', 'is_deleted')

        existing_map = {obj[0]: obj[1] for obj in existing_instances}

        # 检查活跃实例冲突
        active_ids = [iid for iid, is_del in existing_map.items() if not is_del]
        if active_ids:
            active_names = [
                inst["instance_name"] for inst in instances
                if inst["instance_id"] in active_ids
            ]
            raise BaseAppException(f"以下实例已存在:{'、'.join(active_names)}")

        # 分离新实例和需恢复的已删除实例
        new_instances = [inst for inst in instances if inst["instance_id"] not in existing_map]
        deleted_ids = [iid for iid, is_del in existing_map.items() if is_del]

        return new_instances, deleted_ids

    @staticmethod
    def _create_instances_in_db(new_instances, deleted_ids, monitor_object_id):
        """在数据库事务中创建实例、规则和关联关系

        Returns:
            tuple: (created_instance_ids, created_rule_ids)
        """
        created_instance_ids = []
        created_rule_ids = []

        # 清理逻辑删除的实例
        if deleted_ids:
            deleted_count = MonitorInstance.objects.filter(
                id__in=deleted_ids,
                is_deleted=True
            ).delete()[0]
            logger.info(f"清理逻辑删除实例数量: {deleted_count}")

        # 创建默认分组规则
        for instance in new_instances:
            rule_ids = InstanceConfigService.create_default_rule(
                monitor_object_id,
                instance["instance_id"],
                instance["group_ids"]
            )
            if rule_ids:
                created_rule_ids.extend(rule_ids)

        # 构建并批量创建实例及关联关系
        instance_objs, association_objs, created_instance_ids = (
            InstanceConfigService._build_instance_objects(new_instances, monitor_object_id)
        )

        if instance_objs:
            MonitorInstance.objects.bulk_create(
                instance_objs,
                batch_size=DatabaseConstants.BULK_CREATE_BATCH_SIZE
            )

        if association_objs:
            MonitorInstanceOrganization.objects.bulk_create(
                association_objs,
                batch_size=DatabaseConstants.BULK_CREATE_BATCH_SIZE
            )

        return created_instance_ids, created_rule_ids

    @staticmethod
    def _format_instance_ids(instances):
        """格式化实例ID为字符串元组格式"""
        for instance in instances:
            instance["instance_id"] = str(tuple([instance["instance_id"]]))

    @staticmethod
    def _check_existing_instances(instance_ids):
        """检查已存在的实例,返回(已删除ID列表, 活跃ID列表)"""
        existing_instances = MonitorInstance.objects.filter(
            id__in=instance_ids
        ).values_list('id', 'is_deleted')

        existing_map = {obj[0]: obj[1] for obj in existing_instances}
        deleted_ids = [iid for iid, is_del in existing_map.items() if is_del]
        active_ids = [iid for iid, is_del in existing_map.items() if not is_del]

        return deleted_ids, active_ids, existing_map

    @staticmethod
    def _build_instance_objects(new_instances, monitor_object_id):
        """构建实例对象和关联关系,返回(实例列表, 关联列表, ID列表)"""
        instance_objs = []
        association_objs = []
        instance_ids = []

        for instance in new_instances:
            instance_id = instance["instance_id"]
            instance_ids.append(instance_id)

            # 创建实例对象
            instance_objs.append(MonitorInstance(
                id=instance_id,
                name=instance["instance_name"],
                monitor_object_id=monitor_object_id
            ))

            # 创建关联对象
            for group_id in instance["group_ids"]:
                association_objs.append(MonitorInstanceOrganization(
                    monitor_instance_id=instance_id,
                    organization=group_id
                ))

        return instance_objs, association_objs, instance_ids

    @staticmethod
    def create_monitor_instance_by_node_mgmt(data):
        """创建监控对象实例（优化后：使用单一外层事务）"""
        instances = data.get("instances", [])
        monitor_object_id = data["monitor_object_id"]

        logger.info(
            f"开始创建监控实例,monitor_object_id={monitor_object_id}, "
            f"instance_count={len(instances)}"
        )

        # 快速失败:无实例直接返回
        if not instances:
            logger.info("没有需要创建的实例")
            return

        # ============ 阶段1: 参数预校验与数据准备 ============
        try:
            new_instances, deleted_ids = InstanceConfigService._prepare_instances_for_creation(instances)
        except BaseAppException:
            raise
        except Exception as e:
            logger.error(f"实例数据准备失败: {e}", exc_info=True)
            raise BaseAppException(f"实例数据准备失败: {e}")

        if not new_instances and not deleted_ids:
            logger.info("没有需要创建的新实例")
            return

        logger.info(
            f"需要创建 {len(new_instances)} 个新实例,"
            f"需要恢复 {len(deleted_ids)} 个已删除实例"
        )

        # ============ 使用单一外层事务包裹所有操作 ============
        try:
            with transaction.atomic():
                # 阶段2：数据库操作（使用外层事务）
                created_instance_ids, created_rule_ids = InstanceConfigService._create_instances_in_db(
                    new_instances, deleted_ids, monitor_object_id
                )
                logger.info(f"创建实例和规则成功,实例数: {len(created_instance_ids)}")

                # 阶段3：调用 Controller 创建采集配置（使用外层事务）
                data["instances"] = new_instances
                Controller(data).controller()
                logger.info("采集配置创建成功")

                # ✅ 所有操作成功，事务自动提交

        except BaseAppException as e:
            # 业务异常直接抛出（事务已自动回滚）
            logger.error(f"创建监控实例失败: {e}")
            raise
        except Exception as e:
            # 系统异常包装后抛出（事务已自动回滚）
            logger.error(f"创建监控实例失败: {e}", exc_info=True)
            raise BaseAppException(f"创建监控实例失败: {e}")

        logger.info(f"创建监控实例成功,共 {len(created_instance_ids)} 个")

    @staticmethod
    def update_instance_config(child_info, base_info):

        child_env = None

        if base_info:
            config_obj = CollectConfig.objects.filter(id=base_info["id"]).first()
            if config_obj:
                content = ConfigFormat.json_to_yaml(base_info["content"])
                env_config = base_info.get("env_config")
                if env_config:
                    child_env = {k: v for k, v in env_config.items()}
                NodeMgmt().update_config_content(base_info["id"], content, env_config)

        if child_info or child_env:
            config_obj = CollectConfig.objects.filter(id=child_info["id"]).first()
            if not config_obj:
                return
            content = ConfigFormat.json_to_toml(child_info["content"]) if child_info else None
            NodeMgmt().update_child_config_content(child_info["id"], content, child_env)