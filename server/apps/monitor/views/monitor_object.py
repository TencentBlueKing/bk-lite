from django.db.models import Count
from rest_framework import viewsets
from rest_framework.decorators import action

from apps.core.logger import monitor_logger as logger
from apps.core.utils.loader import LanguageLoader
from apps.core.utils.permission_utils import (
    get_permissions_rules,
    check_instance_permission,
)
from apps.core.utils.web_utils import WebUtils
from apps.monitor.constants.language import LanguageConstants
from apps.monitor.constants.permission import PermissionConstants
from apps.monitor.filters.monitor_object import MonitorObjectFilter
from apps.monitor.models import MonitorInstance, MonitorPolicy
from apps.monitor.models.monitor_object import MonitorObject, MonitorObjectType
from apps.monitor.serializers.monitor_object import MonitorObjectSerializer, MonitorObjectTypeSerializer
from apps.monitor.services.monitor_object import MonitorObjectService
from config.drf.pagination import CustomPageNumberPagination


class MonitorObjectViewSet(viewsets.ModelViewSet):
    queryset = MonitorObject.objects.all()
    serializer_class = MonitorObjectSerializer
    filterset_class = MonitorObjectFilter
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        """默认只返回父对象（parent 为空的对象）"""
        queryset = super().get_queryset()
        # 如果请求参数中没有明确指定 parent，则只返回父对象
        if 'parent' not in self.request.query_params:
            queryset = queryset.filter(parent__isnull=True)
        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        results = serializer.data

        lan = LanguageLoader(
            app=LanguageConstants.APP, default_lang=request.user.locale
        )

        # 统计每个对象的子对象数量
        children_counts = MonitorObject.objects.filter(
            parent__isnull=False
        ).values('parent_id').annotate(
            children_count=Count('id')
        )
        children_count_map = {item['parent_id']: item['children_count'] for item in children_counts}

        # 构建类型 id -> name 的映射，用于自定义类型的 fallback 显示
        type_name_map = {t.id: t.name for t in MonitorObjectType.objects.all()}

        for result in results:
            _type_key = f"{LanguageConstants.MONITOR_OBJECT_TYPE}.{result['type']}"
            _name_key = f"{LanguageConstants.MONITOR_OBJECT}.{result['name']}"
            # display_type 优先级：国际化 > 类型名称 > 类型ID
            result["display_type"] = lan.get(_type_key) or type_name_map.get(result["type"]) or result["type"]
            # display_name 优先级：国际化 > 模型字段 display_name > name
            i18n_name = lan.get(_name_key)
            result["display_name"] = i18n_name or result.get("display_name") or result["name"]
            # 添加是否内置标识：有国际化配置 或 没有 display_name 字段 表示内置
            result["is_builtin"] = bool(i18n_name) or not result.get("display_name")
            # 添加子对象数量
            result["children_count"] = children_count_map.get(result["id"], 0)

        if request.GET.get("add_instance_count") in ["true", "True"]:
            include_children = request.COOKIES.get("include_children", "0") == "1"
            current_team = request.COOKIES.get("current_team")

            inst_res = get_permissions_rules(
                request.user,
                current_team,
                "monitor",
                f"{PermissionConstants.INSTANCE_MODULE}",
                include_children=include_children,
            )

            instance_permissions, cur_team = (
                inst_res.get("data", {}),
                inst_res.get("team", []),
            )

            inst_objs = MonitorInstance.objects.filter(
                is_deleted=False
            ).prefetch_related("monitorinstanceorganization_set")
            inst_map = {}
            for inst_obj in inst_objs:
                monitor_object_id = inst_obj.monitor_object_id
                instance_id = inst_obj.id
                teams = {
                    i.organization
                    for i in inst_obj.monitorinstanceorganization_set.all()
                }
                _check = check_instance_permission(
                    monitor_object_id,
                    instance_id,
                    teams,
                    instance_permissions,
                    cur_team,
                )
                if not _check:
                    continue
                if monitor_object_id not in inst_map:
                    inst_map[monitor_object_id] = 0
                inst_map[monitor_object_id] += 1

            for result in results:
                result["instance_count"] = inst_map.get(result["id"], 0)

        if request.GET.get("add_policy_count") in ["true", "True"]:
            include_children = request.COOKIES.get("include_children", "0") == "1"
            policy_res = get_permissions_rules(
                request.user,
                request.COOKIES.get("current_team"),
                "monitor",
                f"{PermissionConstants.POLICY_MODULE}",
                include_children=include_children,
            )

            policy_permissions, cur_team = (
                policy_res.get("data", {}),
                policy_res.get("team", []),
            )

            policy_objs = MonitorPolicy.objects.all().prefetch_related(
                "policyorganization_set"
            )
            policy_map = {}
            for policy_obj in policy_objs:
                monitor_object_id = policy_obj.monitor_object_id
                instance_id = policy_obj.id
                teams = {
                    i.organization for i in policy_obj.policyorganization_set.all()
                }
                _check = check_instance_permission(
                    monitor_object_id, instance_id, teams, policy_permissions, cur_team
                )
                if not _check:
                    continue
                if monitor_object_id not in policy_map:
                    policy_map[monitor_object_id] = 0
                policy_map[monitor_object_id] += 1

            for result in results:
                result["policy_count"] = policy_map.get(result["id"], 0)

        return WebUtils.response_success(results)

    @action(methods=["post"], detail=False, url_path="order")
    def order(self, request):
        MonitorObjectService.set_object_order(request.data)
        return WebUtils.response_success()

    @action(methods=["post"], detail=True, url_path="visibility")
    def visibility(self, request, pk=None):
        """切换对象可见性"""
        obj = self.get_object()
        is_visible = request.data.get("is_visible")
        if is_visible is None:
            return WebUtils.response_error("is_visible is required")
        obj.is_visible = is_visible
        obj.save(update_fields=["is_visible"])
        return WebUtils.response_success()

    def create(self, request, *args, **kwargs):
        """创建监控对象，支持同时创建子对象"""
        data = request.data
        children = data.pop("children", [])
        
        # 创建父对象
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        parent_obj = serializer.save()
        
        # 批量创建子对象
        if children:
            child_objects = []
            for child in children:
                if child.get("id") and child.get("name"):
                    child_objects.append(MonitorObject(
                        name=child["id"],
                        display_name=child["name"],
                        icon=data.get("icon", ""),
                        type_id=data.get("type"),
                        description="",
                        level="derivative",
                        parent=parent_obj,
                        is_visible=True
                    ))
            if child_objects:
                MonitorObject.objects.bulk_create(child_objects)
        
        return WebUtils.response_success(serializer.data)

    def update(self, request, *args, **kwargs):
        """更新监控对象，支持更新/新增子对象"""
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        data = request.data.copy()
        children = data.pop("children", None)
        
        # 更新父对象
        serializer = self.get_serializer(instance, data=data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        
        # 处理子对象
        if children is not None:
            # 获取现有子对象
            existing_children = {child.name: child for child in MonitorObject.objects.filter(parent=instance)}
            
            new_children = []
            for child in children:
                child_id = child.get("id")
                child_name = child.get("name")
                if not child_id or not child_name:
                    continue
                    
                if child_id in existing_children:
                    # 更新已有子对象的 display_name
                    existing_child = existing_children[child_id]
                    if existing_child.display_name != child_name:
                        existing_child.display_name = child_name
                        existing_child.save(update_fields=["display_name"])
                else:
                    # 创建新子对象
                    new_children.append(MonitorObject(
                        name=child_id,
                        display_name=child_name,
                        icon=instance.icon,
                        type_id=instance.type_id,
                        description="",
                        level="derivative",
                        parent=instance,
                        is_visible=True
                    ))
            
            if new_children:
                MonitorObject.objects.bulk_create(new_children)
        
        return WebUtils.response_success(serializer.data)


class MonitorObjectTypeViewSet(viewsets.ModelViewSet):
    """监控对象类型视图"""
    queryset = MonitorObjectType.objects.all()
    serializer_class = MonitorObjectTypeSerializer
    pagination_class = None  # 不分页

    def list(self, request, *args, **kwargs):
        # 排除 id 为 'all' 的类型
        queryset = self.filter_queryset(self.get_queryset()).exclude(id='all')
        
        # 获取语言加载器
        lan = LanguageLoader(
            app=LanguageConstants.APP, default_lang=request.user.locale
        )
        
        # 统计每个类型下的父对象数量（不包括子对象）
        type_object_counts = MonitorObject.objects.filter(
            parent__isnull=True
        ).values('type').annotate(
            object_count=Count('id')
        )
        count_map = {item['type']: item['object_count'] for item in type_object_counts}
        
        serializer = self.get_serializer(queryset, many=True)
        results = serializer.data
        
        for result in results:
            # 添加国际化显示名称
            # 优先级：国际化 > name 字段 > id
            _type_key = f"{LanguageConstants.MONITOR_OBJECT_TYPE}.{result['id']}"
            i18n_name = lan.get(_type_key)
            result["display_name"] = i18n_name or result.get("name") or result["id"]
            # 添加对象数量
            result["object_count"] = count_map.get(result["id"], 0)
            # 添加是否内置标识：有国际化配置表示内置类型
            result["is_builtin"] = bool(i18n_name)
        
        return WebUtils.response_success(results)
