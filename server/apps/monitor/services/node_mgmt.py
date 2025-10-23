import ast

from apps.core.exceptions.base_app_exception import BaseAppException
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
        """存在子模型的要给子模型默认规则"""
        child_objs = MonitorObject.objects.filter(parent_id=monitor_object_id)
        if not child_objs:
            return

        rules = []

        _monitor_instance_id = ast.literal_eval(monitor_instance_id)[0]

        for child_obj in child_objs:
            metric_obj = Metric.objects.filter(monitor_object_id=child_obj.id).first()
            rules.append(MonitorObjectOrganizationRule(
                name=f"{child_obj.name}-{monitor_instance_id}",
                monitor_object_id=child_obj.id,
                rule={
                    "type": "metric",
                    "metric_id": metric_obj.id,
                    "filter": [{"name": "instance_id", "method": "=",  "value": _monitor_instance_id}]
                },
                organizations=group_ids,
                monitor_instance_id=monitor_instance_id,
            ))
        MonitorObjectOrganizationRule.objects.bulk_create(rules, batch_size=DatabaseConstants.BULK_CREATE_BATCH_SIZE)

    @staticmethod
    def create_monitor_instance_by_node_mgmt(data):
        """创建监控对象实例"""

        # 格式化实例id,将实例id统一为字符串元祖（支持多维度组成的实例id）
        for instance in data["instances"]:
            instance["instance_id"] = str(tuple([instance["instance_id"]]))

        # 删除逻辑删除的实例，避免影响现有逻辑
        MonitorInstance.objects.filter(id__in=[instance["instance_id"] for instance in data["instances"]], is_deleted=True).delete()

        # 过滤已存在的实例
        objs = MonitorInstance.objects.filter(id__in=[instance["instance_id"] for instance in data["instances"]])
        instance_set = {obj.id for obj in objs}

        # 格式化实例id,将实例id统一为字符串元祖（支持多维度组成的实例id）
        new_instances, old_instances = [], []
        for instance in data["instances"]:
            if instance["instance_id"] in instance_set:
                old_instances.append(instance)
            else:
                new_instances.append(instance)

        data["instances"] = new_instances

        for instance in data["instances"]:
            # 创建实例默认分组规则
            InstanceConfigService.create_default_rule(data["monitor_object_id"], instance["instance_id"], instance["group_ids"])

        # 实例更新
        instance_map = {
            instance["instance_id"]: {
                "id": instance["instance_id"],
                "name": instance["instance_name"],
                # "interval": instance["interval"],
                "monitor_object_id": data["monitor_object_id"],
                "group_ids": instance["group_ids"],
            }
            for instance in data["instances"]
        }

        creates,  assos = [], []
        for instance_id, instance_info in instance_map.items():
            group_ids = instance_info.pop("group_ids")
            for group_id in group_ids:
                assos.append((instance_id, group_id))
            creates.append(MonitorInstance(**instance_info))

        MonitorInstance.objects.bulk_create(creates, batch_size=DatabaseConstants.BULK_CREATE_BATCH_SIZE)

        MonitorInstanceOrganization.objects.bulk_create(
            [MonitorInstanceOrganization(monitor_instance_id=asso[0], organization=asso[1]) for asso in assos],
            batch_size=DatabaseConstants.BULK_CREATE_BATCH_SIZE
        )

        # 实例配置
        Controller(data).controller()

        if old_instances:
            raise BaseAppException(f"以下实例已存在：{'、'.join([instance['instance_name'] for instance in old_instances])}")

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