import toml
import yaml
from rest_framework.decorators import action
from rest_framework.viewsets import ModelViewSet, ViewSet

from apps.core.utils.permission_utils import get_permissions_rules, check_instance_permission, get_permission_rules, permission_filter, filter_instances_with_permissions
from apps.core.utils.web_utils import WebUtils
from apps.log.constants import POLICY_MODULE, INSTANCE_MODULE, DEFAULT_PERMISSION
from apps.log.models import CollectType, CollectInstance, CollectConfig
from apps.log.models.policy import Policy
from apps.log.serializers.collect_config import CollectTypeSerializer
from apps.log.filters.collect_config import CollectTypeFilter
from apps.log.services.collect_type import CollectTypeService
from apps.rpc.node_mgmt import NodeMgmt


class CollectTypeViewSet(ModelViewSet):
    queryset = CollectType.objects.all()
    serializer_class = CollectTypeSerializer
    filterset_class = CollectTypeFilter

    def list(self, request, *args, **kwargs):
        """
        获取采集类型列表

        支持参数：
        - add_policy_count: 是否计算策略数量，true/false，默认false
        - add_instance_count: 是否计算实例数量，true/false，默认false
        - name: 按名称模糊搜索
        - collector: 按采集器名称模糊搜索
        """
        # 获取基础查询集
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        results = serializer.data

        # 检查是否需要添加策略数量统计（带权限控制）
        if request.GET.get("add_policy_count") in ["true", "True"]:
            # 获取策略权限
            policy_res = get_permissions_rules(
                request.user,
                request.COOKIES.get("current_team"),
                "log",
                POLICY_MODULE,
            )

            policy_permissions, cur_team = policy_res.get("data", {}), policy_res.get("team", [])

            # 获取所有策略并进行权限检查
            policy_objs = Policy.objects.select_related('collect_type').prefetch_related('policyorganization_set').all()
            policy_map = {}

            for policy_obj in policy_objs:
                collect_type_id = str(policy_obj.collect_type_id)
                policy_id = policy_obj.id
                teams = {org.organization for org in policy_obj.policyorganization_set.all()}

                # 使用通用权限检查函数
                _check = check_instance_permission(collect_type_id, policy_id, teams, policy_permissions, cur_team)
                if not _check:
                    continue

                if policy_obj.collect_type_id not in policy_map:
                    policy_map[policy_obj.collect_type_id] = 0
                policy_map[policy_obj.collect_type_id] += 1

            # 添加策略数量到结果中
            for result in results:
                result["policy_count"] = policy_map.get(result["id"], 0)

        # 检查是否需要添加实例数量统计（带权限控制，参考监控模块实现）
        if request.GET.get("add_instance_count") in ["true", "True"]:
            # 获取采集实例权限
            instance_res = get_permissions_rules(
                request.user,
                request.COOKIES.get("current_team"),
                "log",
                INSTANCE_MODULE,
            )

            instance_permissions, cur_team = instance_res.get("data", {}), instance_res.get("team", [])

            # 获取所有采集实例并进行权限检查
            instance_objs = CollectInstance.objects.select_related('collect_type').prefetch_related('collectinstanceorganization_set').all()
            instance_map = {}

            for instance_obj in instance_objs:
                collect_type_id = str(instance_obj.collect_type_id)
                instance_id = instance_obj.id
                teams = {org.organization for org in instance_obj.collectinstanceorganization_set.all()}

                # 使用通用权限检查函数
                _check = check_instance_permission(collect_type_id, instance_id, teams, instance_permissions, cur_team)
                if not _check:
                    continue

                if instance_obj.collect_type_id not in instance_map:
                    instance_map[instance_obj.collect_type_id] = 0
                instance_map[instance_obj.collect_type_id] += 1

            # 添加实例数量到结果中
            for result in results:
                result["instance_count"] = instance_map.get(result["id"], 0)

        return WebUtils.response_success(results)

    @action(methods=['get'], detail=False, url_path='all_attrs')
    def get_all_attrs(self, request):
        """
        获取所有采集类型的属性，并进行去重
        """
        # 获取所有采集类型的属性列表
        collect_types = CollectType.objects.all()

        # 收集所有属性并去重
        all_attrs = set()
        for collect_type in collect_types:
            if collect_type.attrs and isinstance(collect_type.attrs, list):
                all_attrs.update(collect_type.attrs)

        # 转换为排序的列表，保证返回结果的一致性
        unique_attrs = sorted(list(all_attrs))

        return WebUtils.response_success(unique_attrs)


class CollectInstanceViewSet(ViewSet):

    @action(methods=['post'], detail=False, url_path='search')
    def search(self, request):
        """
        查询采集实例列表，支持权限过滤

        权限逻辑：完全参考监控模块的 monitor_instance_list 实现
        """
        collect_type_id = request.data.get("collect_type_id")
        name = request.data.get("name")
        page = int(request.data.get("page", 1))
        page_size = int(request.data.get("page_size", 10))

        # 获取当前用户选择的组织（必填）
        current_team = request.COOKIES.get("current_team")

        if collect_type_id:
            # 单采集类型查询 - 使用与监控模块完全一致的权限检查方式
            permission = get_permission_rules(
                request.user,
                current_team,
                "log",
                f"{INSTANCE_MODULE}.{collect_type_id}",
            )
            # 应用权限过滤（与监控模块保持一致）
            qs = permission_filter(
                CollectInstance,
                permission,
                team_key="collectinstanceorganization__organization__in",
                id_key="id__in"
            )
            # 使用统一的服务层方法
            data = CollectTypeService.search_instance_with_permission(
                collect_type_id=collect_type_id,
                name=name,
                page=page,
                page_size=page_size,
                queryset=qs
            )
            # 添加实例级别权限信息（与监控模块保持一致）
            inst_permission_map = {i["id"]: i["permission"] for i in permission.get("instance", [])}
        else:
            instance_res = get_permissions_rules(
                request.user,
                request.COOKIES.get("current_team"),
                "log",
                INSTANCE_MODULE,
            )
            # 超管权限检查
            admin_cur_team = instance_res.get("all", {}).get("team")
            if admin_cur_team:
                qs = CollectInstance.objects.filter(collectinstanceorganization__organization_in=admin_cur_team)
                inst_permission_map = {}
            else:
                objs = CollectInstance.objects.prefetch_related("collectinstanceorganization_set").all()
                result = []
                for instance in objs:
                    organizations = {
                        org.organization
                        for org in instance.collectinstanceorganization_set.all()
                    }
                    result.append({
                        'instance_id': instance.id,
                        'organizations': organizations,
                        'collect_type_id': instance.collect_type_id
                    })

                permissions, cur_team = instance_res.get("data", {}), instance_res.get("team", [])
                # 使用新的优雅权限过滤方法
                inst_permission_map = filter_instances_with_permissions(result, permissions, cur_team)
                # 获取有权限的实例ID列表
                authorized_instance_ids = list(inst_permission_map.keys())
                if not authorized_instance_ids:
                    # 如果没有任何权限，返回空结果
                    return WebUtils.response_success({"count": 0, "items": []})
                # 重新查询数据库，获取有权限的实例完整信息
                qs = CollectInstance.objects.filter(id__in=authorized_instance_ids)
            # 使用统一的服务层方法
            data = CollectTypeService.search_instance_with_permission(
                collect_type_id=None,
                name=name,
                page=page,
                page_size=page_size,
                queryset=qs
            )

        for instance_info in data["items"]:
            if instance_info["id"] in inst_permission_map:
                instance_info["permission"] = inst_permission_map[instance_info["id"]]
            else:
                instance_info["permission"] = DEFAULT_PERMISSION

        return WebUtils.response_success(data)

    @action(methods=['post'], detail=False, url_path='batch_create')
    def batch_create(self, request):
        CollectTypeService.batch_create_collect_configs(request.data)
        return WebUtils.response_success()

    @action(methods=['post'], detail=False, url_path='remove_collect_instance')
    def remove_collect_instance(self, request):
        instance_ids = request.data.get("instance_ids", [])
        config_objs = CollectConfig.objects.filter(collect_instance_id__in=instance_ids)
        child_configs, configs = [], []
        for config in config_objs:
            if config.is_child:
                child_configs.append(config.id)
            else:
                configs.append(config.id)
        # 删除子配置
        NodeMgmt().delete_child_configs(child_configs)
        # 删除配置
        NodeMgmt().delete_configs(configs)
        # 删除配置对象
        config_objs.delete()
        CollectInstance.objects.filter(id__in=instance_ids).delete()
        return WebUtils.response_success()


    @action(methods=['post'], detail=False, url_path='instance_update')
    def instance_update(self, request):
        CollectTypeService.update_instance(
            request.data.get("instance_id"),
            request.data.get("name"),
            request.data.get("organizations", []),
        )
        return WebUtils.response_success()

    @action(methods=['post'], detail=False, url_path='set_organizations')
    def set_organizations(self, request):
        """设置监控对象实例组织"""
        instance_ids = request.data.get("instance_ids", [])
        organizations = request.data.get("organizations", [])
        CollectTypeService.set_instances_organizations(instance_ids, organizations)
        return WebUtils.response_success()


class CollectConfigViewSet(ViewSet):

    @action(methods=['post'], detail=False, url_path='get_config_content')
    def get_config_content(self, request):
        config_objs = CollectConfig.objects.filter(id__in=request.data["ids"])
        if not config_objs:
            return WebUtils.response_error("配置不存在!")

        result = {}
        for config_obj in config_objs:
            content_key = "content" if config_obj.is_child else "config_template"
            if config_obj.is_child:
                configs = NodeMgmt().get_child_configs_by_ids([config_obj.id])
            else:
                configs = NodeMgmt().get_configs_by_ids([config_obj.id])
            config = configs[0]

            if config_obj.file_type == "yaml":
                config["content"] = yaml.safe_load(config[content_key])
            else:
                config["content"] = toml.loads(config[content_key])

            if config_obj.is_child:
                result["child"] = config
            else:
                result["base"] = config

        return WebUtils.response_success(result)

    @action(methods=['post'], detail=False, url_path='update_instance_collect_config')
    def update_instance_collect_config(self, request):
        CollectTypeService.update_instance_config_v2(
            request.data.get("child"),
            request.data.get("base"),
            request.data.get("instance_id"),
            request.data.get("collect_type_id"),
        )
        return WebUtils.response_success()
