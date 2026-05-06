from django.db import transaction
from django.db import models
from django.db.models import Q

from apps.core.exceptions.base_app_exception import BaseAppException, UnauthorizedException
from apps.core.utils.permission_utils import get_permission_rules
from apps.core.logger import monitor_logger as logger
from apps.monitor.constants.database import DatabaseConstants
from apps.monitor.constants.permission import PermissionConstants
from apps.monitor.models import (
    MonitorInstance,
    MonitorInstanceOrganization,
    CollectConfig,
    MonitorObject,
    MonitorObjectOrganizationRule,
    Metric,
)
from apps.monitor.utils.dimension import parse_instance_id
from apps.monitor.utils.config_format import ConfigFormat
from apps.monitor.utils.plugin_controller import Controller
from apps.rpc.node_mgmt import NodeMgmt
from apps.system_mgmt.models import User
from apps.system_mgmt.utils.group_utils import GroupUtils


class InstanceConfigService:
    DEFAULT_GROUPING_METRIC_BY_OBJECT = {
        "Pod": "pod_status_phase",
        "Node": "node_status_condition",
    }

    @staticmethod
    def _build_permission_data(actor_context):
        return {
            "username": actor_context["username"],
            "domain": actor_context["domain"],
            "current_team": actor_context["current_team"],
            "include_children": actor_context.get("include_children", False),
        }

    @staticmethod
    def _build_actor_user(actor_context):
        return User(username=actor_context["username"], domain=actor_context["domain"])

    @staticmethod
    def _get_actor_scope_groups(actor_context):
        if actor_context.get("is_superuser"):
            return None
        return GroupUtils.get_user_authorized_child_groups(
            actor_context.get("group_list", []),
            actor_context["current_team"],
            include_children=actor_context.get("include_children", False),
        )

    @classmethod
    def _get_authorized_monitor_instances(cls, actor_context, monitor_object_id, require_operate=False):
        if actor_context.get("is_superuser"):
            return MonitorInstance.objects.filter(monitor_object_id=monitor_object_id)

        permission = get_permission_rules(
            cls._build_actor_user(actor_context),
            actor_context["current_team"],
            "monitor",
            f"{PermissionConstants.INSTANCE_MODULE}.{monitor_object_id}",
            include_children=actor_context.get("include_children", False),
        )
        team_ids = permission.get("team", [])
        instance_permissions = permission.get("instance", [])
        allowed_instance_ids = [
            item["id"]
            for item in instance_permissions
            if isinstance(item, dict) and "id" in item and (not require_operate or "Operate" in item.get("permission", []))
        ]

        queryset = MonitorInstance.objects.filter(monitor_object_id=monitor_object_id)
        if team_ids and allowed_instance_ids:
            return queryset.filter(Q(monitorinstanceorganization__organization__in=team_ids) | Q(id__in=allowed_instance_ids)).distinct()
        if team_ids:
            return queryset.filter(monitorinstanceorganization__organization__in=team_ids).distinct()
        if allowed_instance_ids:
            return queryset.filter(id__in=allowed_instance_ids)
        return queryset.none()

    @classmethod
    def _get_authorized_collect_configs(cls, ids, actor_context=None, require_operate=False):
        config_ids = list({str(config_id) for config_id in ids if config_id not in (None, "")})
        if not config_ids:
            return []

        config_objs = list(CollectConfig.objects.filter(id__in=config_ids).select_related("monitor_instance__monitor_object"))
        if not config_objs:
            return []

        if actor_context is None:
            return config_objs

        if actor_context.get("is_superuser"):
            return config_objs

        configs_by_object = {}
        for config_obj in config_objs:
            configs_by_object.setdefault(config_obj.monitor_instance.monitor_object_id, []).append(config_obj)

        authorized_ids = set()
        for monitor_object_id, object_configs in configs_by_object.items():
            instance_ids = {
                instance_id
                for instance_id in cls._get_authorized_monitor_instances(
                    actor_context,
                    monitor_object_id,
                    require_operate=require_operate,
                ).values_list("id", flat=True)
            }
            for config_obj in object_configs:
                if config_obj.monitor_instance_id in instance_ids:
                    authorized_ids.add(config_obj.id)

        if len(authorized_ids) != len(config_ids):
            raise UnauthorizedException("无权限访问指定采集配置")

        return [config_obj for config_obj in config_objs if config_obj.id in authorized_ids]

    @classmethod
    def _ensure_instance_access(cls, collect_instance_id, actor_context=None, require_operate=False):
        instance = MonitorInstance.objects.select_related("monitor_object").filter(id=collect_instance_id).first()
        if not instance:
            raise BaseAppException("监控实例不存在")
        if actor_context is None:
            return instance
        if actor_context.get("is_superuser"):
            return instance
        authorized = (
            cls._get_authorized_monitor_instances(
                actor_context,
                instance.monitor_object_id,
                require_operate=require_operate,
            )
            .filter(id=collect_instance_id)
            .exists()
        )
        if not authorized:
            raise UnauthorizedException("无权限访问指定监控实例")
        return instance

    @classmethod
    def _sanitize_instances_for_onboarding(cls, instances, actor_context):
        if actor_context.get("is_superuser"):
            authorized_scope_groups = None
        else:
            authorized_scope_groups = set(cls._get_actor_scope_groups(actor_context) or [])
            if not authorized_scope_groups:
                raise UnauthorizedException("当前组织无可用权限范围")

        requested_node_ids = set()
        for instance in instances:
            node_ids = instance.get("node_ids", [])
            if not node_ids:
                raise BaseAppException(f"实例 {instance.get('instance_name', instance.get('instance_id', 'unknown'))} 缺少 node_ids")
            requested_node_ids.update(str(node_id) for node_id in node_ids if node_id not in (None, ""))

        authorized_nodes = NodeMgmt().get_authorized_nodes_by_ids(
            list(requested_node_ids),
            cls._build_permission_data(actor_context),
        )
        authorized_node_map = {str(node["id"]): node for node in authorized_nodes}
        unauthorized_node_ids = sorted(requested_node_ids - set(authorized_node_map))
        if unauthorized_node_ids:
            raise UnauthorizedException(f"存在无权限节点: {', '.join(unauthorized_node_ids)}")

        sanitized_instances = []
        for instance in instances:
            node_ids = []
            group_ids = set()
            for raw_node_id in instance.get("node_ids", []):
                node_id = str(raw_node_id)
                node_info = authorized_node_map.get(node_id)
                if not node_info:
                    raise UnauthorizedException(f"节点 {node_id} 无权限访问")
                node_ids.append(node_id)
                node_groups = set(node_info.get("organization_ids", []))
                if authorized_scope_groups is not None:
                    node_groups &= authorized_scope_groups
                if not node_groups:
                    raise UnauthorizedException(f"节点 {node_id} 不在当前组织授权范围内")
                group_ids.update(node_groups)

            sanitized_instance = {**instance}
            sanitized_instance["node_ids"] = node_ids
            sanitized_instance["group_ids"] = sorted(group_ids)
            sanitized_instances.append(sanitized_instance)
        return sanitized_instances

    @classmethod
    def _get_default_group_metric(cls, child_obj):
        preferred_metric_name = cls.DEFAULT_GROUPING_METRIC_BY_OBJECT.get(child_obj.name)
        if preferred_metric_name:
            metric_obj = Metric.objects.filter(monitor_object_id=child_obj.id, name=preferred_metric_name).first()
            if metric_obj:
                return metric_obj
            logger.warning(f"子对象 {child_obj.id} 默认分组指标 {preferred_metric_name} 不存在，回退到首个指标")

        return Metric.objects.filter(monitor_object_id=child_obj.id).first()

    @staticmethod
    def _sync_existing_instance_attrs(existing_instances, deleted_ids):
        """同步复用/恢复实例的可变属性（除主键外）

        通过页面接入链路复用或恢复的实例，都应视为手动接入实例，
        不再受自动发现任务生命周期管理影响，因此需要统一纠正为 auto=False。
        """
        if not existing_instances:
            return 0

        instances_to_update = []
        for instance in existing_instances:
            instances_to_update.append(
                MonitorInstance(
                    id=instance["instance_id"],
                    name=instance.get("instance_name", ""),
                    auto=False,
                    is_deleted=False,
                    is_active=True,
                )
            )

        fields = ["name", "auto", "is_active"]
        if deleted_ids:
            fields.append("is_deleted")

        MonitorInstance.objects.bulk_update(
            instances_to_update,
            fields,
            batch_size=DatabaseConstants.BULK_CREATE_BATCH_SIZE,
        )
        return len(instances_to_update)

    @staticmethod
    def get_config_content(ids, actor_context=None):
        result = {}
        config_objs = InstanceConfigService._get_authorized_collect_configs(
            ids,
            actor_context,
            require_operate=False,
        )
        if not config_objs:
            return result

        for config_obj in config_objs:
            content_key = "content" if config_obj.is_child else "config_template"
            if config_obj.is_child:
                configs = NodeMgmt().get_child_configs_by_ids([config_obj.id])
            else:
                configs = NodeMgmt().get_configs_by_ids([config_obj.id])
            config = configs[0]
            if config_obj.file_type == "toml":
                config["content"] = ConfigFormat.toml_to_dict(config[content_key])
            elif config_obj.file_type == "yaml":
                config["content"] = ConfigFormat.yaml_to_dict(config[content_key])
            else:
                raise BaseAppException("file_type must be toml or yaml")
            if config_obj.is_child:
                result["child"] = config
            else:
                result["base"] = config
        return result

    @staticmethod
    def get_instance_configs(collect_instance_id, actor_context=None):
        """获取实例配置"""

        InstanceConfigService._ensure_instance_access(
            collect_instance_id,
            actor_context,
            require_operate=False,
        )

        config_objs = CollectConfig.objects.filter(monitor_instance_id=collect_instance_id)

        configs = []

        for config_obj in config_objs:
            configs.append(
                {
                    "config_id": config_obj.id,
                    "collector": config_obj.collector,
                    "collect_type": config_obj.collect_type,
                    "config_type": config_obj.config_type,
                    "monitor_plugin_id": config_obj.monitor_plugin_id,
                    "instance_id": collect_instance_id,
                    "is_child": config_obj.is_child,
                }
            )

        result = {}
        for config in configs:
            key = (
                config.get("monitor_plugin_id") or config["collect_type"],
                config["config_type"],
            )
            if key not in result:
                result[key] = {
                    "instance_id": config["instance_id"],
                    "collect_type": config["collect_type"],
                    "config_type": config["config_type"],
                    "monitor_plugin_id": config.get("monitor_plugin_id"),
                    "config_ids": [config["config_id"]],
                }
            else:
                result[key]["config_ids"].append(config["config_id"])

        items = list(result.values())
        for item in items:
            config_content = InstanceConfigService.get_config_content(item["config_ids"], actor_context)
            item.update(config_content=config_content)

        return items

    @staticmethod
    def create_default_rule(monitor_object_id, monitor_instance_id, group_ids):
        """存在子模型的要给子模型默认规则

        返回创建的规则ID列表，用于失败时回滚
        """
        child_objs = MonitorObject.objects.filter(parent_id=monitor_object_id)
        if not child_objs:
            return []

        rules = []
        _monitor_instance_id = parse_instance_id(monitor_instance_id)[0]

        for child_obj in child_objs:
            metric_obj = InstanceConfigService._get_default_group_metric(child_obj)
            if not metric_obj:
                logger.warning(f"子对象 {child_obj.id} 没有关联指标，跳过规则创建")
                continue

            rules.append(
                MonitorObjectOrganizationRule(
                    name=f"{child_obj.name}-{_monitor_instance_id}",
                    monitor_object_id=child_obj.id,
                    rule={
                        "type": "metric",
                        "metric_id": metric_obj.id,
                        "filter": [
                            {
                                "name": "instance_id",
                                "method": "=",
                                "value": _monitor_instance_id,
                            }
                        ],
                    },
                    organizations=group_ids,
                    monitor_instance_id=monitor_instance_id,
                )
            )

        if rules:
            created_rules = MonitorObjectOrganizationRule.objects.bulk_create(rules, batch_size=DatabaseConstants.BULK_CREATE_BATCH_SIZE)
            return [rule.id for rule in created_rules]

        return []

    @staticmethod
    def _batch_create_default_rules(instances, monitor_object_id):
        """批量为多个实例创建默认分组规则

        Args:
            instances: 实例列表，每个实例包含 instance_id 和 group_ids
            monitor_object_id: 监控对象ID

        Returns:
            list: 创建的规则ID列表
        """
        if not instances:
            return []

        # 一次性查询子对象和指标，避免重复查询
        child_objs = MonitorObject.objects.filter(parent_id=monitor_object_id).prefetch_related(
            models.Prefetch("metric_set", queryset=Metric.objects.all())
        )

        if not child_objs:
            return []

        # 构建子对象到指标的映射
        child_metric_map = {}
        for child_obj in child_objs:
            metric_obj = InstanceConfigService._get_default_group_metric(child_obj)
            if metric_obj:
                child_metric_map[child_obj.id] = (child_obj, metric_obj)
            else:
                logger.warning(f"子对象 {child_obj.id} 没有关联指标，跳过规则创建")

        if not child_metric_map:
            return []

        # 批量构建所有规则
        all_rules = []
        for instance in instances:
            instance_id = instance["instance_id"]
            group_ids = instance["group_ids"]
            _monitor_instance_id = parse_instance_id(instance_id)[0]

            for child_id, (child_obj, metric_obj) in child_metric_map.items():
                all_rules.append(
                    MonitorObjectOrganizationRule(
                        name=f"{child_obj.name}-{_monitor_instance_id}",
                        monitor_object_id=child_obj.id,
                        rule={
                            "type": "metric",
                            "metric_id": metric_obj.id,
                            "filter": [
                                {
                                    "name": "instance_id",
                                    "method": "=",
                                    "value": _monitor_instance_id,
                                }
                            ],
                        },
                        organizations=group_ids,
                        monitor_instance_id=instance_id,
                    )
                )

        # 批量创建所有规则
        if all_rules:
            created_rules = MonitorObjectOrganizationRule.objects.bulk_create(all_rules, batch_size=DatabaseConstants.BULK_CREATE_BATCH_SIZE)
            logger.info(f"批量创建默认规则数量: {len(created_rules)}")
            return [rule.id for rule in created_rules]

        return []

    @staticmethod
    def _prepare_instances_for_creation(instances, monitor_object_id, collect_type, collector, configs):
        """准备待创建实例:格式化ID、检查已存在实例、分类处理、校验配置冲突

        Args:
            instances: 实例列表
            monitor_object_id: 监控对象ID
            collect_type: 采集类型
            collector: 采集器名称
            configs: 配置列表，包含将要创建的 config_type

        Returns:
            tuple: (new_instances, existing_instances, deleted_ids)

        Raises:
            BaseAppException: 当配置已存在时抛出异常
        """
        # 格式化实例ID
        for instance in instances:
            instance["instance_id"] = str(tuple([instance["instance_id"]]))

        # 检查已存在的实例（只需要查询 is_deleted 字段）
        instance_ids = [inst["instance_id"] for inst in instances]
        existing_instances_qs = MonitorInstance.objects.filter(id__in=instance_ids, monitor_object_id=monitor_object_id).values_list(
            "id", "is_deleted"
        )

        existing_map = {obj[0]: obj[1] for obj in existing_instances_qs}  # {id: is_deleted}

        # 提取将要创建的 config_type 列表
        config_types_to_create = {config.get("type") for config in configs if config.get("type")}

        # 检查已存在的配置（避免重复创建相同采集配置）
        if config_types_to_create:
            existing_configs = CollectConfig.objects.filter(
                monitor_instance_id__in=instance_ids,
                collector=collector,
                collect_type=collect_type,
                config_type__in=config_types_to_create,
            ).values_list("monitor_instance_id", "config_type")

            # 构建已存在配置的映射: {instance_id: set(config_types)}
            config_map = {}
            for instance_id, config_type in existing_configs:
                if instance_id not in config_map:
                    config_map[instance_id] = set()
                config_map[instance_id].add(config_type)

            # 检查冲突并抛出异常
            for inst in instances:
                instance_id = inst["instance_id"]
                if instance_id in config_map:
                    conflicting_types = config_map[instance_id] & config_types_to_create
                    if conflicting_types:
                        raise BaseAppException(
                            f"实例 '{inst.get('instance_name', instance_id)}' 已存在采集配置，无法重复创建。"
                            f"采集器={collector}, 采集类型={collect_type}, "
                            f"冲突的配置类型={', '.join(sorted(conflicting_types))}"
                        )

        # 分类实例
        new_instances = []  # 完全不存在的实例
        existing_instances = []  # 已存在的实例（需要复用）
        deleted_ids = []  # 已删除的实例（需要恢复）

        for inst in instances:
            instance_id = inst["instance_id"]

            if instance_id not in existing_map:
                # 完全不存在，需要创建
                new_instances.append(inst)
            else:
                # 已存在
                if existing_map[instance_id]:  # is_deleted == True
                    # 已删除，需要恢复
                    deleted_ids.append(instance_id)
                    existing_instances.append(inst)
                else:
                    # 活跃实例，复用它
                    existing_instances.append(inst)
                    logger.info(f"实例 {inst.get('instance_name', instance_id)} 已存在，将复用该实例并添加新的采集配置")

        return new_instances, existing_instances, deleted_ids

    @staticmethod
    def _create_instances_in_db(new_instances, existing_instances, deleted_ids, monitor_object_id):
        """在数据库事务中创建实例、更新已存在实例、规则和关联关系

        Returns:
            tuple: (created_instance_ids, created_rule_ids)
        """
        created_instance_ids = []
        created_rule_ids = []

        if existing_instances:
            updated_count = InstanceConfigService._sync_existing_instance_attrs(existing_instances, deleted_ids)
            logger.info(f"复用已存在实例数量: {len(existing_instances)}, 同步属性并激活: {updated_count}, 恢复已删除实例: {len(deleted_ids)}")

            # 为已存在的实例创建组织关联（如果还没有）
            for instance in existing_instances:
                instance_id = instance["instance_id"]
                for group_id in instance["group_ids"]:
                    MonitorInstanceOrganization.objects.get_or_create(monitor_instance_id=instance_id, organization=group_id)

        # 批量创建实例的默认分组规则（优化：一次性查询+批量创建）
        instances_to_process = new_instances + existing_instances
        if instances_to_process:
            rule_ids = InstanceConfigService._batch_create_default_rules(instances_to_process, monitor_object_id)
            if rule_ids:
                created_rule_ids.extend(rule_ids)

        # 构建并批量创建新实例及关联关系
        instance_objs, association_objs, created_instance_ids = InstanceConfigService._build_instance_objects(new_instances, monitor_object_id)

        if instance_objs:
            MonitorInstance.objects.bulk_create(instance_objs, batch_size=DatabaseConstants.BULK_CREATE_BATCH_SIZE)

        if association_objs:
            MonitorInstanceOrganization.objects.bulk_create(association_objs, batch_size=DatabaseConstants.BULK_CREATE_BATCH_SIZE)

        return created_instance_ids, created_rule_ids

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
            instance_objs.append(
                MonitorInstance(
                    id=instance_id,
                    name=instance["instance_name"],
                    monitor_object_id=monitor_object_id,
                )
            )

            # 创建关联对象
            for group_id in instance["group_ids"]:
                association_objs.append(MonitorInstanceOrganization(monitor_instance_id=instance_id, organization=group_id))

        return instance_objs, association_objs, instance_ids

    @staticmethod
    def create_monitor_instance_by_node_mgmt(data, actor_context=None):
        """创建监控对象实例（支持同一实例ID多种采集方式）"""
        instances = data.get("instances", [])
        monitor_object_id = data["monitor_object_id"]
        collect_type = data.get("collect_type", "")
        collector = data.get("collector", "")
        monitor_plugin_id = data.get("monitor_plugin_id")

        # 快速失败:无实例直接返回
        if not instances:
            logger.info("没有需要创建的实例")
            return

        sanitized_instances = instances
        if actor_context is not None:
            sanitized_instances = InstanceConfigService._sanitize_instances_for_onboarding(instances, actor_context)

        # ============ 阶段1: 参数预校验与数据准备 ============
        try:
            new_instances, existing_instances, deleted_ids = InstanceConfigService._prepare_instances_for_creation(
                sanitized_instances,
                monitor_object_id,
                collect_type,
                collector,
                data.get("configs", []),
            )
        except BaseAppException:
            raise
        except Exception as e:
            logger.error(f"实例数据准备失败: {e}", exc_info=True)
            raise BaseAppException(f"实例数据准备失败: {e}")

        if not new_instances and not existing_instances:
            logger.info("没有需要处理的实例")
            return

        logger.info(
            f"需要创建 {len(new_instances)} 个新实例,需要复用 {len(existing_instances)} 个已存在实例,其中需要恢复 {len(deleted_ids)} 个已删除实例"
        )

        # ============ 使用单一外层事务包裹所有操作 ============
        try:
            with transaction.atomic():
                # 阶段2：数据库操作（使用外层事务）
                created_instance_ids, created_rule_ids = InstanceConfigService._create_instances_in_db(
                    new_instances,
                    existing_instances,
                    deleted_ids,
                    monitor_object_id,
                )
                logger.info(f"创建实例和规则成功,实例数: {len(created_instance_ids)}")

                # 阶段3：调用 Controller 创建采集配置（使用外层事务）
                # 注意：所有实例（新建+已存在）都需要创建采集配置
                sanitized_data = {**data}
                sanitized_data["instances"] = new_instances + existing_instances
                sanitized_data["monitor_plugin_id"] = monitor_plugin_id
                Controller(sanitized_data).controller()
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

        logger.info(f"创建监控实例成功,共 {len(created_instance_ids)} 个新实例,{len(existing_instances)} 个复用实例")

    @staticmethod
    def update_instance_config(child_info, base_info, actor_context=None):
        config_ids = []
        if base_info and base_info.get("id"):
            config_ids.append(base_info["id"])
        if child_info and child_info.get("id"):
            config_ids.append(child_info["id"])

        config_objs = InstanceConfigService._get_authorized_collect_configs(
            config_ids,
            actor_context,
            require_operate=True,
        )
        config_map = {config.id: config for config in config_objs}

        if base_info and child_info:
            base_config = config_map.get(base_info["id"])
            child_config = config_map.get(child_info["id"])
            if base_config and child_config and base_config.monitor_instance_id != child_config.monitor_instance_id:
                raise BaseAppException("基础配置与子配置不属于同一监控实例")

        if base_info:
            config_obj = config_map.get(base_info["id"])
            if config_obj:
                content = ConfigFormat.json_to_yaml(base_info["content"])
                env_config = base_info.get("env_config")
                NodeMgmt().update_config_content(base_info["id"], content, env_config)

        if child_info:
            config_obj = config_map.get(child_info["id"])
            if not config_obj:
                return
            env_config = child_info.get("env_config")
            content = ConfigFormat.json_to_toml(child_info["content"]) if child_info else None
            NodeMgmt().update_child_config_content(child_info["id"], content, env_config)
