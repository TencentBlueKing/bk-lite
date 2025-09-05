from collections import defaultdict

import toml
import yaml
from django.db import transaction

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.log.models import CollectInstance, CollectInstanceOrganization, CollectConfig, CollectType
from apps.log.plugins.controller import Controller
from apps.rpc.node_mgmt import NodeMgmt


class CollectTypeService:
    @staticmethod
    def get_collect_type(collect_type: str) -> str:
        """
        Get the collect type based on the provided string.

        Args:
            collect_type (str): The type of collection.

        Returns:
            str: The corresponding collect type.
        """
        return collect_type.lower() if collect_type else "unknown"

    @staticmethod
    def batch_create_collect_configs(data: dict) -> list:
        """
        Batch create collect configurations based on the provided data.

        Args:
            data (dict): The data containing collector, collect_type, configs, and instances.

        Returns:
            list: A list of created collect configurations.
        """

        # 过滤已存在的实例
        objs = CollectInstance.objects.filter(id__in=[instance["instance_id"] for instance in data["instances"]])
        instance_set = {obj.id for obj in objs}

        # 格式化实例id,将实例id统一为字符串元祖（支持多维度组成的实例id）
        new_instances, old_instances = [], []
        for instance in data["instances"]:
            if instance["instance_id"] in instance_set:
                old_instances.append(instance)
            else:
                new_instances.append(instance)

        data["instances"] = new_instances

        # 实例更新
        instance_map = {
            instance["instance_id"]: {
                "id": instance["instance_id"],
                "name": instance["instance_name"],
                "collect_type_id": data["collect_type_id"],
                "node_id": instance["node_ids"][0],
                "group_ids": instance["group_ids"],
            }
            for instance in data["instances"]
        }

        creates, assos = [], []
        for instance_id, instance_info in instance_map.items():
            group_ids = instance_info.pop("group_ids")
            for group_id in group_ids:
                assos.append((instance_id, group_id))
            creates.append(CollectInstance(**instance_info))

        CollectInstance.objects.bulk_create(creates, batch_size=200)

        if assos:
            CollectInstanceOrganization.objects.bulk_create(
                [CollectInstanceOrganization(collect_instance_id=asso[0], organization=asso[1]) for asso in assos],
                batch_size=200
            )

        # 实例配置
        Controller(data).controller()

        if old_instances:
            raise BaseAppException(
                f"以下实例已存在：{'、'.join([instance['instance_name'] for instance in old_instances])}")

    @staticmethod
    def set_instances_organizations(instance_ids, organizations):
        """设置监控对象实例组织"""
        if not instance_ids or not organizations:
            return

        with transaction.atomic():
            # 删除旧的组织关联
            CollectInstanceOrganization.objects.filter(
                collect_instance_id__in=instance_ids
            ).delete()

            # 添加新的组织关联
            creates = []
            for instance_id in instance_ids:
                for org in organizations:
                    creates.append(CollectInstanceOrganization(
                        collect_instance_id=instance_id,
                        organization=org
                    ))
            CollectInstanceOrganization.objects.bulk_create(creates, ignore_conflicts=True)

    @staticmethod
    def update_instance_config(child_info, base_info):

        child_env = None

        if base_info:
            config_obj = CollectConfig.objects.filter(id=base_info["id"]).first()
            if config_obj:
                content = yaml.dump(base_info["content"], default_flow_style=False)
                env_config = base_info.get("env_config")
                if env_config:
                    child_env = {k: v for k, v in env_config.items()}
                NodeMgmt().update_config_content(base_info["id"], content, env_config)

        if child_info or child_env:
            config_obj = CollectConfig.objects.filter(id=child_info["id"]).first()
            if not config_obj:
                return
            content = toml.dumps(child_info["content"]) if child_info else None
            NodeMgmt().update_child_config_content(child_info["id"], content, child_env)

    @staticmethod
    def update_instance_config_v2(child_info, base_info, instance_id, collect_type_id):
        """ 更新对象实例配置 """
        child_env = None
        collect_type_obj = CollectType.objects.filter(id=collect_type_id).first()
        if not collect_type_obj:
            raise BaseAppException("collect_type does not exist")

        col_obj = Controller(
            {
                "collector": collect_type_obj.collector,
                "collect_type": collect_type_obj.name,
                "collect_type_id": collect_type_id,
                "instances": [{"instance_id": instance_id}],
            }
        )

        if base_info:
            config_obj = CollectConfig.objects.filter(id=base_info["id"]).first()
            if config_obj:
                content = col_obj.render_config_template_content("base", base_info["content_data"], instance_id)
                env_config = base_info.get("env_config")
                if env_config:
                    child_env = {k: v for k, v in env_config.items()}
                NodeMgmt().update_config_content(base_info["id"], content, env_config)

        if child_info or child_env:
            config_obj = CollectConfig.objects.filter(id=child_info["id"]).first()
            if not config_obj:
                return
            content = col_obj.render_config_template_content("child", child_info["content_data"], instance_id)
            NodeMgmt().update_child_config_content(child_info["id"], content, child_env)

    @staticmethod
    def update_instance(instance_id, name, organizations):
        """更新监控对象实例"""
        instance = CollectInstance.objects.filter(id=instance_id).first()
        if not instance:
            raise BaseAppException("collect instance does not exist")
        if name:
            instance.name = name
            instance.save()

        # 更新组织信息
        instance.collectinstanceorganization_set.all().delete()
        for org in organizations:
            instance.collectinstanceorganization_set.create(organization=org)

    @staticmethod
    def search_instance(collect_type_id, name, page, page_size, current_team, accessible_instance_ids=None):
        """
        查询采集实例列表

        Args:
            collect_type_id: 采集类型ID，可选
            name: 实例名称，可选，支持模糊查询
            page: 页码
            page_size: 每页数量
            current_team: 当前组织ID，必填
            accessible_instance_ids: 有权限访问的实例ID列表，可选，用于权限过滤
        """
        queryset = CollectInstance.objects.select_related("collect_type")

        # 根据当前组织过滤采集实例（必填条件）
        queryset = queryset.filter(
            collectinstanceorganization__organization=current_team
        )

        if collect_type_id:
            queryset = queryset.filter(collect_type_id=collect_type_id)
        if name:
            queryset = queryset.filter(name__icontains=name)

        # 如果提供了权限过滤的实例ID列表，则进一步过滤
        if accessible_instance_ids is not None:
            queryset = queryset.filter(id__in=accessible_instance_ids)

        # 计算总数
        total_count = queryset.count()
        # 计算分页
        start = (page - 1) * page_size
        end = page * page_size
        # 获取当前页的数据
        data_list = queryset.values("id", "name", "node_id", "collect_type_id", "collect_type__name", "collect_type__collector")[start:end]

        instance_ids = [item["id"] for item in data_list]

        # 补充组织与配置
        org_map = defaultdict(list)
        org_objs = CollectInstanceOrganization.objects.filter(
            collect_instance_id__in=instance_ids
        ).values_list("collect_instance_id", "organization")
        for instance_id, organization in org_objs:
            org_map[instance_id].append(organization)

        conf_map = defaultdict(list)
        conf_objs = CollectConfig.objects.filter(
            collect_instance_id__in=instance_ids
        ).values_list("collect_instance", "id")
        for instance_id, config_id in conf_objs:
            conf_map[instance_id].append(config_id)

        nodes = NodeMgmt().node_list(dict(page_size=-1))
        node_map = {node["id"]: node["name"] for node in nodes["nodes"]}

        items = []
        for info in data_list:
            info.update(
                organization=org_map.get(info["id"]),
                config_id=conf_map.get(info["id"]),
                node_name=node_map.get(info["node_id"], ""),
            )
            items.append(info)

        data = {"count": total_count, "items": items}

        return data

    @staticmethod
    def search_instance_with_permission(collect_type_id, name, page, page_size, current_team, queryset):
        """
        使用权限过滤后的查询集查询采集实例列表（参考监控模块实现）

        Args:
            collect_type_id: 采集类型ID，必填
            name: 实例名称，可选，支持模糊查询
            page: 页码
            page_size: 每页数量
            current_team: 当前组织ID，必填
            queryset: 已经权限过滤的查询集（已包含组织过滤）
        """
        # 应用业务过滤条件（不需要再次过滤组织，因为权限过滤已经处理了）
        queryset = queryset.filter(collect_type_id=collect_type_id)

        if name:
            queryset = queryset.filter(name__icontains=name)

        # 去重并关联查询
        queryset = queryset.distinct().select_related('collect_type')

        # 计算总数
        total_count = queryset.count()

        # 计算分页
        start = (page - 1) * page_size
        end = start + page_size

        # 获取当前页的数据
        page_data = queryset[start:end]

        # 获取实例ID列表用于补充额外信息
        instance_ids = [instance.id for instance in page_data]

        # 补充组织与配置信息
        org_map = defaultdict(list)
        org_objs = CollectInstanceOrganization.objects.filter(
            collect_instance_id__in=instance_ids
        ).values_list("collect_instance_id", "organization")
        for instance_id, organization in org_objs:
            org_map[instance_id].append(organization)

        conf_map = defaultdict(list)
        conf_objs = CollectConfig.objects.filter(
            collect_instance_id__in=instance_ids
        ).values_list("collect_instance", "id")
        for instance_id, config_id in conf_objs:
            conf_map[instance_id].append(config_id)

        # 获取节点信息
        nodes = NodeMgmt().node_list(dict(page_size=-1))
        node_map = {node["id"]: node["name"] for node in nodes["nodes"]}

        # 构建结果（与监控模块格式保持一致，使用 results 字段）
        items = []
        for instance in page_data:
            item = {
                "id": instance.id,
                "instance_id": instance.id,  # 添加 instance_id 字段以兼容权限映射
                "name": instance.name,
                "node_id": instance.node_id,
                "collect_type_id": instance.collect_type_id,
                "collect_type__name": instance.collect_type.name,
                "collect_type__collector": instance.collect_type.collector,
                "organization": org_map.get(instance.id, []),
                "config_id": conf_map.get(instance.id, []),
                "node_name": node_map.get(instance.node_id, ""),
            }
            items.append(item)

        return {"count": total_count, "results": items, "items": items}  # 同时提供两个字段以保证兼容性
