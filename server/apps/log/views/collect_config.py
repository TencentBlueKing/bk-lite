import toml
import yaml
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from rest_framework.decorators import action
from rest_framework.viewsets import ModelViewSet, ViewSet

from apps.core.utils.loader import LanguageLoader
from apps.core.utils.permission_utils import (
    get_permissions_rules,
    get_instance_permissions,
    get_instance_permission_map,
    get_permission_rules,
    permission_filter,
)
from apps.core.utils.web_utils import WebUtils
from apps.log.constants.collect_type import DISPLAY_CATEGORY_ORDER
from apps.log.constants.language import LanguageConstants
from apps.log.constants.permission import PermissionConstants
from apps.log.models import (
    CollectConfig,
    CollectInstance,
    CollectInstanceOrganization,
    CollectType,
)
from apps.log.models.policy import Policy
from apps.log.serializers.collect_config import CollectTypeSerializer
from apps.log.filters.collect_config import CollectTypeFilter
from apps.log.services.collect_type import CollectTypeService
from apps.log.services.access_scope import LogAccessScopeService
from apps.log.services.search import SearchService
from apps.rpc.node_mgmt import NodeMgmt
from apps.core.utils.team_utils import get_current_team


def should_hide_collect_type_entry(result: dict) -> bool:
    return result.get("collector") == "Packetbeat" and result.get("name") == "http"


def parse_collect_config_content(config_obj, raw_content: str):
    if config_obj.file_type != "yaml":
        return toml.loads(raw_content)

    if config_obj.is_child:
        collect_type = config_obj.collect_instance.collect_type
        if collect_type.collector == "Packetbeat" and collect_type.name == "flows":
            # Packetbeat 的父配置已声明 packetbeat.protocols，子配置按该节点追加协议列表，
            # 同时还会追加顶层 packetbeat.flows；读取编辑表单时需补回父级上下文。
            raw_content = f"packetbeat.protocols:\n{raw_content}"
    return yaml.safe_load(raw_content)


class CollectTypeViewSet(ModelViewSet):
    queryset = CollectType.objects.all()
    serializer_class = CollectTypeSerializer
    filterset_class = CollectTypeFilter

    LOG_GROUP_CREATE_SCOPE = "log_group_create"

    @staticmethod
    def _escape_logsql_value(value):
        return str(value).replace("\\", "\\\\").replace('"', '\\"')

    @classmethod
    def _build_instance_scope_query(cls, instance_ids):
        expressions = [
            f'instance_id:"{cls._escape_logsql_value(instance_id)}"'
            for instance_id in instance_ids
        ]
        if not expressions:
            return ""
        if len(expressions) == 1:
            return expressions[0]
        return f"({' OR '.join(expressions)})"

    @classmethod
    def _append_creation_scope_filter(cls, query, instance_ids):
        scope_query = cls._build_instance_scope_query(instance_ids)
        if not scope_query:
            return ""

        base_query = (query or "").strip()
        if not base_query or base_query == "*":
            return scope_query
        return f"({base_query}) AND {scope_query}"

    @staticmethod
    def _is_log_group_create_scope(request):
        return (
            request.query_params.get("scope")
            == CollectTypeViewSet.LOG_GROUP_CREATE_SCOPE
        )

    @staticmethod
    def _get_accessible_count_map(
        model,
        organization_relation,
        permissions,
        current_teams,
        collect_type_ids,
    ):
        """Count accessible objects without materializing every object and organization."""
        collect_type_ids = list(collect_type_ids)
        if not collect_type_ids:
            return {}

        permissions = permissions if isinstance(permissions, dict) else {}
        organization_lookup = f"{organization_relation}__organization__in"
        permission_scope = Q(pk__in=[])

        all_permission = permissions.get("all") or {}
        if isinstance(all_permission, dict) and all_permission.get("team"):
            permission_scope |= Q(
                **{
                    organization_lookup: CollectTypeViewSet._matching_team_ids(
                        all_permission["team"],
                        nested_ids=True,
                    )
                }
            )

        for collect_type_id in collect_type_ids:
            collect_type_permission = permissions.get(str(collect_type_id))
            object_scope = Q(pk__in=[])

            if collect_type_permission and isinstance(collect_type_permission, dict):
                instance_ids = CollectTypeViewSet._matching_primary_keys(
                    model,
                    collect_type_permission.get("instance", []),
                )
                if instance_ids:
                    object_scope |= Q(pk__in=instance_ids)

                team_ids = CollectTypeViewSet._matching_team_ids(
                    collect_type_permission.get("team", []),
                    nested_ids=True,
                )
            else:
                # Preserve check_instance_permission's fallback for object types
                # without an explicit permission rule.
                team_ids = CollectTypeViewSet._matching_team_ids(current_teams)

            if team_ids:
                object_scope |= Q(**{organization_lookup: team_ids})

            permission_scope |= Q(collect_type_id=collect_type_id) & object_scope

        counts = (
            model.objects.filter(collect_type_id__in=collect_type_ids)
            .filter(permission_scope)
            .values("collect_type_id")
            .annotate(count=Count("id", distinct=True))
        )
        return {item["collect_type_id"]: item["count"] for item in counts}

    @staticmethod
    def _matching_team_ids(values, nested_ids=False):
        """Keep the integer IDs that can intersect model-side organization IDs."""
        if not isinstance(values, (list, tuple, set)):
            return []
        result = []
        for value in values:
            if nested_ids and isinstance(value, dict):
                value = value.get("id")
            if isinstance(value, int):
                result.append(value)
        return result

    @staticmethod
    def _matching_primary_keys(model, instance_permissions):
        """Mirror get_instance_permissions' string-normalized primary-key match."""
        if not isinstance(instance_permissions, list):
            return []

        primary_keys = []
        primary_key_field = model._meta.pk
        for item in instance_permissions:
            if not isinstance(item, dict) or item.get("id") is None:
                continue
            permission_id = item["id"]
            try:
                primary_key = primary_key_field.to_python(permission_id)
            except (TypeError, ValueError, ValidationError):
                continue
            if str(primary_key) == str(permission_id):
                primary_keys.append(primary_key)
        return primary_keys

    def _get_log_group_create_attrs(self, request, query, start_time, end_time):
        try:
            organization_ids = LogAccessScopeService.get_manageable_organization_ids(
                request
            )
        except ValueError as exc:
            return WebUtils.response_error(error_message=str(exc), status_code=403)

        if not organization_ids:
            return WebUtils.response_error(error_message="当前用户无权限创建日志分组", status_code=403)

        instance_ids = list(
            CollectInstanceOrganization.objects.filter(
                organization__in=list(organization_ids)
            )
            .order_by("collect_instance_id")
            .values_list("collect_instance_id", flat=True)
            .distinct()
        )
        final_query = self._append_creation_scope_filter(query, instance_ids)
        if not final_query:
            return WebUtils.response_success([])

        data = SearchService.all_field_names(
            final_query, start_time, end_time, [], resolved_groups=[]
        )
        return WebUtils.response_success(data)

    @action(methods=["get"], detail=False, url_path="display_category_enum")
    def display_category_enum(self, request, *args, **kwargs):
        lan = LanguageLoader(app=LanguageConstants.APP, default_lang=request.user.locale)

        categories = []
        for code in DISPLAY_CATEGORY_ORDER:
            lang_key = f"{LanguageConstants.DISPLAY_CATEGORY}.{code}"
            categories.append(
                {
                    "id": code,
                    "name": lan.get(f"{lang_key}.name") or code,
                }
            )

        return WebUtils.response_success(categories)

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
        results = [result for result in serializer.data if not should_hide_collect_type_entry(result)]

        # 加载语言包
        lan = LanguageLoader(app=LanguageConstants.APP, default_lang=request.user.locale)

        # 为每个采集类型添加翻译后的名称和描述
        for result in results:
            collector = result.get("collector")
            name = result.get("name")
            if collector and name:
                # 组装语言配置Key: collect_type.{collector}.{name}
                lan_key = f"{LanguageConstants.COLLECT_TYPE}.{collector}.{name}"
                # 获取翻译后的名称和描述
                result["display_name"] = lan.get(f"{lan_key}.name") or result.get("name", "")
                result["display_description"] = lan.get(f"{lan_key}.description") or result.get("description", "")

        # 检查是否需要添加策略数量统计（带权限控制）
        if request.GET.get("add_policy_count") in ["true", "True"]:
            # 获取策略权限
            include_children = request.COOKIES.get("include_children", "0") == "1"
            policy_res = get_permissions_rules(
                request.user,
                get_current_team(request),
                "log",
                PermissionConstants.POLICY_MODULE,
                include_children=include_children,
            )

            policy_permissions, cur_team = (
                policy_res.get("data", {}),
                policy_res.get("team", []),
            )

            policy_map = self._get_accessible_count_map(
                Policy,
                "policyorganization",
                policy_permissions,
                cur_team,
                (result["id"] for result in results),
            )

            # 添加策略数量到结果中
            for result in results:
                result["policy_count"] = policy_map.get(result["id"], 0)

        # 检查是否需要添加实例数量统计（带权限控制，参考监控模块实现）
        if request.GET.get("add_instance_count") in ["true", "True"]:
            # 获取采集实例权限
            include_children = request.COOKIES.get("include_children", "0") == "1"
            instance_res = get_permissions_rules(
                request.user,
                get_current_team(request),
                "log",
                PermissionConstants.INSTANCE_MODULE,
                include_children=include_children,
            )

            instance_permissions, cur_team = (
                instance_res.get("data", {}),
                instance_res.get("team", []),
            )

            instance_map = self._get_accessible_count_map(
                CollectInstance,
                "collectinstanceorganization",
                instance_permissions,
                cur_team,
                (result["id"] for result in results),
            )

            # 添加实例数量到结果中
            for result in results:
                result["instance_count"] = instance_map.get(result["id"], 0)

        return WebUtils.response_success(results)

    @action(methods=["get"], detail=False, url_path="all_attrs")
    def get_all_attrs(self, request):
        """
        根据当前搜索条件动态获取属性列表
        """
        query = request.query_params.get("query", "*")
        start_time = request.query_params.get("start_time", "")
        end_time = request.query_params.get("end_time", "")
        log_groups = request.query_params.getlist("log_groups") or request.query_params.getlist("log_groups[]")

        if self._is_log_group_create_scope(request):
            return self._get_log_group_create_attrs(request, query, start_time, end_time)

        try:
            scope = LogAccessScopeService.resolve_scope(request, log_groups)
        except ValueError as exc:
            return WebUtils.response_error(error_message=str(exc), status_code=403)

        data = SearchService.all_field_names(query, start_time, end_time, scope.log_groups, resolved_groups=scope.resolved_group_objects)

        return WebUtils.response_success(data)


class CollectInstanceViewSet(ViewSet):
    OPERATE_PERMISSION = "Operate"
    PAGE_SIZE_MAX = 500
    PAGE_SIZE_ALL = -1

    @staticmethod
    def _normalize_ids(values):
        if not values:
            return []
        if not isinstance(values, list):
            values = [values]
        return [str(value) for value in values if value is not None and str(value) != ""]

    @staticmethod
    def _normalize_orgs(values):
        if not values:
            return set()
        if not isinstance(values, list):
            values = [values]
        orgs = set()
        for value in values:
            try:
                orgs.add(int(value))
            except (TypeError, ValueError):
                continue
        return orgs

    @classmethod
    def _normalize_page_params(cls, request_data):
        try:
            page = int(request_data.get("page", 1))
            page_size = int(request_data.get("page_size", 10))
        except (TypeError, ValueError) as exc:
            raise ValueError("page and page_size must be integers") from exc

        if page < 1:
            raise ValueError("page must be greater than or equal to 1")
        if page_size == cls.PAGE_SIZE_ALL:
            return page, page_size
        if page_size < 1 or page_size > cls.PAGE_SIZE_MAX:
            raise ValueError(f"page_size must be between 1 and {cls.PAGE_SIZE_MAX}")
        return page, page_size

    def _get_permission_context(self, request):
        include_children = request.COOKIES.get("include_children", "0") == "1"
        permission_result = get_permissions_rules(
            request.user,
            get_current_team(request),
            "log",
            PermissionConstants.INSTANCE_MODULE,
            include_children=include_children,
        )
        if not isinstance(permission_result, dict):
            permission_result = {}
        return permission_result.get("data", {}), self._normalize_orgs(permission_result.get("team", []))

    @staticmethod
    def _instance_orgs(instance):
        return {rel.organization for rel in instance.collectinstanceorganization_set.all()}

    def _permissions_for_instance(self, instance, permission_data, current_teams):
        return get_instance_permissions(
            instance.collect_type_id,
            instance.id,
            self._instance_orgs(instance),
            permission_data,
            current_teams,
        )

    def _allowed_organization_scope(self, permission_data, current_teams, collect_type_id=None):
        allowed = set(current_teams)
        allowed |= self._normalize_orgs(permission_data.get("all", {}).get("team", []))

        if collect_type_id is not None:
            type_permission = permission_data.get(str(collect_type_id), {})
            allowed |= self._normalize_orgs(type_permission.get("team", []))
        else:
            for key, type_permission in permission_data.items():
                if key == "all" or not isinstance(type_permission, dict):
                    continue
                allowed |= self._normalize_orgs(type_permission.get("team", []))

        return allowed

    def _authorize_instances(self, request, instance_ids, required_permission=OPERATE_PERMISSION):
        normalized_ids = self._normalize_ids(instance_ids)
        if not normalized_ids:
            return None, WebUtils.response_error(error_message="instance_ids is required")

        instances = list(
            CollectInstance.objects.filter(id__in=normalized_ids).select_related("collect_type").prefetch_related("collectinstanceorganization_set")
        )
        instance_map = {str(instance.id): instance for instance in instances}
        missing_ids = [instance_id for instance_id in normalized_ids if instance_id not in instance_map]
        if missing_ids:
            return None, WebUtils.response_error(error_message="collect instance does not exist")

        permission_data, current_teams = self._get_permission_context(request)
        for instance_id in normalized_ids:
            permissions = self._permissions_for_instance(instance_map[instance_id], permission_data, current_teams)
            if required_permission not in permissions:
                return None, WebUtils.response_403("User does not have permission to operate this instance")

        return instances, None

    def _authorize_target_organizations(self, request, organizations, collect_type_id=None):
        target_orgs = self._normalize_orgs(organizations)
        if not target_orgs:
            return None
        permission_data, current_teams = self._get_permission_context(request)
        allowed_orgs = self._allowed_organization_scope(permission_data, current_teams, collect_type_id)
        if not target_orgs.issubset(allowed_orgs):
            return WebUtils.response_403("User does not have permission to assign instances to these organizations")
        return None

    def _extract_batch_instance_organizations(self, request_data):
        organizations = set()
        for instance in request_data.get("instances", []):
            organizations |= self._normalize_orgs(instance.get("group_ids", []))
        return list(organizations)

    def _build_all_collect_type_scope(self, permission_data, current_teams):
        admin_team_ids = self._normalize_orgs(permission_data.get("all", {}).get("team", []))
        if admin_team_ids:
            return (
                CollectInstance.objects.filter(collectinstanceorganization__organization__in=list(admin_team_ids)).distinct(),
                True,
            )

        current_team_ids = self._normalize_orgs(current_teams)
        restricted_type_ids = set()
        scope_query = Q()
        has_scope = False

        for collect_type_id, type_permission in permission_data.items():
            if collect_type_id == "all" or not isinstance(type_permission, dict):
                continue

            team_ids = self._normalize_orgs(type_permission.get("team", []))
            instance_ids = self._normalize_ids(
                [
                    instance_permission.get("id")
                    for instance_permission in type_permission.get("instance", [])
                    if isinstance(instance_permission, dict)
                ]
            )

            if team_ids or instance_ids:
                restricted_type_ids.add(str(collect_type_id))

            if team_ids:
                scope_query |= Q(
                    collect_type_id=collect_type_id,
                    collectinstanceorganization__organization__in=list(team_ids),
                )
                has_scope = True

            if instance_ids:
                scope_query |= Q(collect_type_id=collect_type_id, id__in=instance_ids)
                has_scope = True

        if current_team_ids:
            fallback_query = Q(collectinstanceorganization__organization__in=list(current_team_ids))
            if restricted_type_ids:
                fallback_query &= ~Q(collect_type_id__in=list(restricted_type_ids))
            scope_query |= fallback_query
            has_scope = True

        if not has_scope:
            return CollectInstance.objects.none(), False

        return CollectInstance.objects.filter(scope_query).distinct(), False

    def _apply_all_type_permissions(self, data, permission_data, current_teams, is_admin_scope):
        if is_admin_scope:
            for instance_info in data["items"]:
                instance_info["permission"] = PermissionConstants.DEFAULT_PERMISSION
            return data

        for instance_info in data["items"]:
            permissions = get_instance_permissions(
                instance_info.get("collect_type_id"),
                instance_info["id"],
                set(instance_info.get("organization", [])),
                permission_data,
                current_teams,
            )
            instance_info["permission"] = permissions or PermissionConstants.DEFAULT_PERMISSION

        return data

    @action(methods=["post"], detail=False, url_path="search")
    def search(self, request):
        """
        查询采集实例列表，支持权限过滤

        权限逻辑：完全参考监控模块的 monitor_instance_list 实现
        """
        collect_type_id = request.data.get("collect_type_id")
        name = request.data.get("name")
        try:
            page, page_size = self._normalize_page_params(request.data)
        except ValueError as exc:
            return WebUtils.response_error(error_message=str(exc))

        # 获取当前用户选择的组织（必填）
        current_team = get_current_team(request)

        if collect_type_id:
            # 单采集类型查询 - 使用与监控模块完全一致的权限检查方式
            include_children = request.COOKIES.get("include_children", "0") == "1"
            permission = get_permission_rules(
                request.user,
                current_team,
                "log",
                f"{PermissionConstants.INSTANCE_MODULE}.{collect_type_id}",
                include_children=include_children,
            )
            # 应用权限过滤（与监控模块保持一致）
            qs = permission_filter(
                CollectInstance,
                permission,
                team_key="collectinstanceorganization__organization__in",
                id_key="id__in",
            )
            # 使用统一的服务层方法
            data = CollectTypeService.search_instance_with_permission(
                collect_type_id=collect_type_id,
                name=name,
                page=page,
                page_size=page_size,
                queryset=qs,
            )
            # 添加实例级别权限信息（与监控模块保持一致）
            inst_permission_map = get_instance_permission_map(permission)
        else:
            permission_data, current_teams = self._get_permission_context(request)
            qs, is_admin_scope = self._build_all_collect_type_scope(permission_data, current_teams)
            # 使用统一的服务层方法
            data = CollectTypeService.search_instance_with_permission(
                collect_type_id=None,
                name=name,
                page=page,
                page_size=page_size,
                queryset=qs,
            )
            data = self._apply_all_type_permissions(data, permission_data, current_teams, is_admin_scope)
            return WebUtils.response_success(data)

        for instance_info in data["items"]:
            if instance_info["id"] in inst_permission_map:
                instance_info["permission"] = inst_permission_map[instance_info["id"]]
            else:
                instance_info["permission"] = PermissionConstants.DEFAULT_PERMISSION

        return WebUtils.response_success(data)

    @action(methods=["post"], detail=False, url_path="batch_create")
    def batch_create(self, request):
        error_response = self._authorize_target_organizations(
            request,
            self._extract_batch_instance_organizations(request.data),
            request.data.get("collect_type_id"),
        )
        if error_response:
            return error_response
        CollectTypeService.batch_create_collect_configs(request.data)
        return WebUtils.response_success()

    @action(methods=["post"], detail=False, url_path="remove_collect_instance")
    def remove_collect_instance(self, request):
        instance_ids = request.data.get("instance_ids", [])
        _, error_response = self._authorize_instances(request, instance_ids)
        if error_response:
            return error_response
        config_objs = CollectConfig.objects.filter(collect_instance_id__in=instance_ids)
        child_configs, configs = [], []
        for config in config_objs:
            if config.is_child:
                child_configs.append(config.id)
            else:
                configs.append(config.id)
        # 删除子配置
        if child_configs:
            NodeMgmt().delete_child_configs(child_configs)
        # 删除配置
        if configs:
            NodeMgmt().delete_configs(configs)
        # 删除配置对象
        config_objs.delete()
        CollectInstance.objects.filter(id__in=instance_ids).delete()
        return WebUtils.response_success()

    @action(methods=["post"], detail=False, url_path="instance_update")
    def instance_update(self, request):
        instance_id = request.data.get("instance_id")
        instances, error_response = self._authorize_instances(request, [instance_id])
        if error_response:
            return error_response
        error_response = self._authorize_target_organizations(
            request,
            request.data.get("organizations", []),
            instances[0].collect_type_id,
        )
        if error_response:
            return error_response
        CollectTypeService.update_instance(
            instance_id,
            request.data.get("name"),
            request.data.get("organizations", []),
        )
        return WebUtils.response_success()

    @action(methods=["post"], detail=False, url_path="set_organizations")
    def set_organizations(self, request):
        """设置监控对象实例组织"""
        instance_ids = request.data.get("instance_ids", [])
        organizations = request.data.get("organizations", [])
        instances, error_response = self._authorize_instances(request, instance_ids)
        if error_response:
            return error_response
        collect_type_ids = {instance.collect_type_id for instance in instances}
        for collect_type_id in collect_type_ids:
            error_response = self._authorize_target_organizations(request, organizations, collect_type_id)
            if error_response:
                return error_response
        CollectTypeService.set_instances_organizations(instance_ids, organizations)
        return WebUtils.response_success()


class CollectConfigViewSet(ViewSet):
    @staticmethod
    def _extract_config_instance_ids(config_objs):
        return list({config_obj.collect_instance_id for config_obj in config_objs})

    def _authorize_config_instances(self, request, config_objs, required_permission="Operate"):
        instance_ids = self._extract_config_instance_ids(config_objs)
        helper = CollectInstanceViewSet()
        _, error_response = helper._authorize_instances(request, instance_ids, required_permission)
        return error_response

    @action(methods=["post"], detail=False, url_path="get_config_content")
    def get_config_content(self, request):
        config_objs = list(
            CollectConfig.objects.filter(id__in=request.data["ids"]).select_related(
                "collect_instance__collect_type"
            )
        )
        if not config_objs:
            return WebUtils.response_error("配置不存在!")
        error_response = self._authorize_config_instances(request, config_objs, required_permission="View")
        if error_response:
            return error_response

        result = {}
        for config_obj in config_objs:
            content_key = "content" if config_obj.is_child else "config_template"
            if config_obj.is_child:
                configs = NodeMgmt().get_child_configs_by_ids([config_obj.id])
            else:
                configs = NodeMgmt().get_configs_by_ids([config_obj.id])
            config = configs[0]

            config["content"] = parse_collect_config_content(config_obj, config[content_key])

            if config_obj.is_child:
                result["child"] = config
            else:
                result["base"] = config

        return WebUtils.response_success(result)

    @action(methods=["post"], detail=False, url_path="update_instance_collect_config")
    def update_instance_collect_config(self, request):
        child = request.data.get("child")
        base = request.data.get("base")
        instance_id = request.data.get("instance_id")
        collect_type_id = request.data.get("collect_type_id")

        if isinstance(child, dict) and child.get("content") is None:
            return WebUtils.response_error("child.content is required")
        if isinstance(base, dict) and base.get("content") is None:
            return WebUtils.response_error("base.content is required")
        instances, error_response = CollectInstanceViewSet()._authorize_instances(request, [instance_id])
        if error_response:
            return error_response
        if str(instances[0].collect_type_id) != str(collect_type_id):
            return WebUtils.response_error(error_message="collect_type does not match instance")

        CollectTypeService.update_instance_config_v2(
            child,
            base,
            request.data.get("instance_id"),
            request.data.get("collect_type_id"),
        )
        return WebUtils.response_success()
