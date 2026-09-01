from django.db import transaction
from django.db.models import Count, Q
from rest_framework import viewsets
from rest_framework.decorators import action

from apps.core.decorators.api_permission import HasPermission
from apps.core.exceptions.base_app_exception import ValidationAppException
from apps.core.user_habit import column_preference_habit_key
from apps.core.utils.loader import LanguageLoader
from apps.core.utils.permission_utils import check_instance_permission, get_permissions_rules
from apps.core.utils.team_utils import get_current_team
from apps.core.utils.web_utils import WebUtils
from apps.monitor.constants.language import LanguageConstants
from apps.monitor.constants.permission import PermissionConstants
from apps.monitor.filters.monitor_object import MonitorObjectFilter
from apps.monitor.models import MonitorInstance, MonitorInstanceOrganization, MonitorPolicy, PolicyOrganization
from apps.monitor.models.monitor_object import MonitorObject, MonitorObjectType
from apps.monitor.models.user_habit import UserHabit
from apps.monitor.serializers.monitor_object import MonitorObjectSerializer, MonitorObjectTypeSerializer
from apps.monitor.serializers.view_column_preference import MonitorViewColumnPreferenceSerializer
from apps.monitor.services.monitor_object import MonitorObjectService
from apps.monitor.services.monitor_object_cleanup import MonitorObjectCleanupPolicyService
from apps.monitor.utils.display_fields import build_display_column_key, validate_display_fields
from apps.monitor.utils.instance_id_keys import resolve_monitor_object_instance_id_keys
from config.drf.pagination import CustomPageNumberPagination

MAX_CANDIDATE_TEAM_ID = 2_147_483_647
MAX_CANDIDATE_TEAM_ID_TEXT = str(MAX_CANDIDATE_TEAM_ID)


def _normalize_candidate_values(values):
    if not isinstance(values, (list, tuple, set)):
        return set()

    normalized = set()
    for value in values:
        if isinstance(value, dict):
            value = value.get("id")
        if value is None:
            continue
        try:
            normalized.add(value)
        except TypeError:
            continue
    return normalized


def _normalize_candidate_team_ids(values):
    normalized = set()
    for value in _normalize_candidate_values(values):
        if type(value) is int:
            team_id = value
        elif isinstance(value, str) and value.isascii() and value.isdigit() and not value.startswith("0"):
            if len(value) > len(MAX_CANDIDATE_TEAM_ID_TEXT) or (len(value) == len(MAX_CANDIDATE_TEAM_ID_TEXT) and value > MAX_CANDIDATE_TEAM_ID_TEXT):
                continue
            team_id = int(value)
        else:
            continue
        if 0 < team_id <= MAX_CANDIDATE_TEAM_ID:
            normalized.add(team_id)
    return normalized


def _build_instance_count_queryset(instance_permissions, cur_team):
    candidate_teams = _normalize_candidate_team_ids(cur_team)
    candidate_instance_ids = set()

    if isinstance(instance_permissions, dict):
        for permission in instance_permissions.values():
            if not isinstance(permission, dict):
                continue
            candidate_teams.update(_normalize_candidate_team_ids(permission.get("team", [])))
            candidate_instance_ids.update(_normalize_candidate_values(permission.get("instance", [])))

    queryset = MonitorInstance.objects.filter(
        is_deleted=False,
        is_active=True,
    ).prefetch_related("monitorinstanceorganization_set")
    if not candidate_teams and not candidate_instance_ids:
        return queryset.none()

    candidate_filter = Q()
    if candidate_teams:
        candidate_filter |= Q(monitorinstanceorganization__organization__in=candidate_teams)
    if candidate_instance_ids:
        candidate_filter |= Q(id__in=candidate_instance_ids)
    return queryset.filter(candidate_filter).distinct()


def _build_org_map_for_ids(model, id_field: str, ids: list) -> dict:
    """分块加载 id→组织集合，避免一次性巨大 IN 查询。"""
    org_map: dict = {}
    chunk_size = 2000
    for start in range(0, len(ids), chunk_size):
        chunk = ids[start : start + chunk_size]
        for entity_id, organization in model.objects.filter(**{f"{id_field}__in": chunk}).values_list(id_field, "organization"):
            org_map.setdefault(entity_id, set()).add(organization)
    return org_map


def _count_by_object_with_permissions(rows, org_map, permissions, cur_team):
    """对 (id, monitor_object_id) 行按权限累计每个对象的可见数量。"""
    counts = {}
    for entity_id, monitor_object_id in rows:
        teams = org_map.get(entity_id, set())
        if not check_instance_permission(
            monitor_object_id,
            entity_id,
            teams,
            permissions,
            cur_team,
        ):
            continue
        counts[monitor_object_id] = counts.get(monitor_object_id, 0) + 1
    return counts


def _build_instance_count_map(instance_permissions, cur_team):
    """按权限统计各对象实例数，避免把完整 ORM 实例装入内存。"""
    rows = list(_build_instance_count_queryset(instance_permissions, cur_team).values_list("id", "monitor_object_id"))
    if not rows:
        return {}
    org_map = _build_org_map_for_ids(MonitorInstanceOrganization, "monitor_instance_id", [row[0] for row in rows])
    return _count_by_object_with_permissions(rows, org_map, instance_permissions, cur_team)


def _build_policy_count_map(policy_permissions, cur_team):
    """按权限统计各对象策略数，只取 id / object_id / 组织关系。"""
    # 权限规则仍要求逐策略判定；此处只拉 id 三元组，避免装载完整 Policy ORM。
    rows = list(MonitorPolicy.objects.all().values_list("id", "monitor_object_id"))
    if not rows:
        return {}
    org_map = _build_org_map_for_ids(PolicyOrganization, "policy_id", [row[0] for row in rows])
    return _count_by_object_with_permissions(rows, org_map, policy_permissions, cur_team)


class MonitorObjectViewSet(viewsets.ModelViewSet):
    queryset = MonitorObject.objects.all()
    serializer_class = MonitorObjectSerializer
    filterset_class = MonitorObjectFilter
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        """默认返回所有对象（父+子），传 parent_only=true 时只返回父对象"""
        queryset = super().get_queryset().select_related("type")
        if "parent" in self.request.query_params:
            return queryset
        if self.request.query_params.get("parent_only") in ["true", "True"]:
            queryset = queryset.filter(parent__isnull=True)
        return queryset

    @staticmethod
    def _translate_display_fields(lan, object_name, display_fields, customized=False):
        """展示列名国际化。

        未自定义的默认列取绑定指标在当前账号语言下的译名；用户通过弹窗自定义过展示列后，
        display_fields[].name 是明确的列头配置，必须原样返回，不能再被指标译名覆盖。
        带 role 的语义列（如云平台子对象 IP）只借指标定位 label，列头由前端按 role 渲染，
        同样不能被指标译名覆盖。
        不就地修改入参，返回新副本。
        """
        if not display_fields:
            return display_fields
        translated = []
        for col in display_fields:
            metrics = col.get("metrics") or []
            metric_name = metrics[0].get("metric") if metrics else None
            new_name = col.get("name")
            if metric_name and not customized and not col.get("role"):
                key = f"{LanguageConstants.MONITOR_OBJECT_METRIC}.{object_name}.{metric_name}.name"
                new_name = lan.get(key) or new_name
            translated.append(
                {
                    **col,
                    "name": new_name,
                    "column_key": build_display_column_key(col),
                }
            )
        return translated

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        results = serializer.data

        lan = LanguageLoader(app=LanguageConstants.APP, default_lang=request.user.locale)

        # 统计每个对象的子对象数量
        children_counts = MonitorObject.objects.filter(parent__isnull=False).values("parent_id").annotate(children_count=Count("id"))
        children_count_map = {item["parent_id"]: item["children_count"] for item in children_counts}

        for result in results:
            _type_key = f"{LanguageConstants.MONITOR_OBJECT_TYPE}.{result['type']}"
            _name_key = f"{LanguageConstants.MONITOR_OBJECT}.{result['name']}"
            # display_type 优先级：国际化 > 类型名称 > 类型ID(英文 slug)
            i18n_type = lan.get(_type_key)
            result["display_type"] = i18n_type or (result.get("type_info") or {}).get("name") or result["type"]
            # display_name 优先级：国际化 > 模型字段 display_name > name(英文 slug)
            i18n_name = lan.get(_name_key)
            result["display_name"] = i18n_name or result.get("display_name") or result["name"]
            # 添加子对象数量
            result["children_count"] = children_count_map.get(result["id"], 0)
            # 展示列名国际化：默认列跟随语言，自定义列保留用户输入。
            result["display_fields"] = self._translate_display_fields(
                lan,
                result["name"],
                result.get("display_fields"),
                result.get("display_fields_customized", False),
            )

        if request.GET.get("add_instance_count") in ["true", "True"]:
            include_children = request.COOKIES.get("include_children", "0") == "1"
            current_team = get_current_team(request)

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

            inst_map = _build_instance_count_map(instance_permissions, cur_team)

            for result in results:
                result["instance_count"] = inst_map.get(result["id"], 0)

        if request.GET.get("add_policy_count") in ["true", "True"]:
            include_children = request.COOKIES.get("include_children", "0") == "1"
            policy_res = get_permissions_rules(
                request.user,
                get_current_team(request),
                "monitor",
                f"{PermissionConstants.POLICY_MODULE}",
                include_children=include_children,
            )

            policy_permissions, cur_team = (
                policy_res.get("data", {}),
                policy_res.get("team", []),
            )

            policy_map = _build_policy_count_map(policy_permissions, cur_team)

            for result in results:
                result["policy_count"] = policy_map.get(result["id"], 0)

        return WebUtils.response_success(results)

    @action(methods=["post"], detail=False, url_path="order")
    @HasPermission("object-Edit")
    def order(self, request):
        MonitorObjectService.set_object_order(request.data)
        return WebUtils.response_success()

    @action(methods=["post"], detail=True, url_path="visibility")
    @HasPermission("object-Edit")
    def visibility(self, request, pk=None):
        """切换对象可见性，同时级联到子对象。"""
        obj = self.get_object()
        is_visible = request.data.get("is_visible")
        if is_visible is None:
            return WebUtils.response_error("is_visible is required")
        MonitorObjectService.set_object_visibility(obj, bool(is_visible))
        return WebUtils.response_success()

    @action(methods=["post"], detail=True, url_path="display_fields")
    @HasPermission("object-Edit")
    def display_fields(self, request, pk=None):
        """保存对象的视图列表展示列配置（用户自定义后 re-seed 不再覆盖）"""
        obj = self.get_object()
        try:
            normalized = validate_display_fields(obj, request.data.get("display_fields", []))
        except Exception as e:
            return WebUtils.response_error(error_message=str(e))
        obj.display_fields = normalized
        obj.display_fields_customized = True
        obj.save(update_fields=["display_fields", "display_fields_customized"])
        return WebUtils.response_success(normalized)

    @HasPermission("object-Delete")
    def destroy(self, request, *args, **kwargs):
        """内置对象的定义与生命周期受保护，运行配置使用独立 action 管理。"""
        instance = self.get_object()
        if instance.is_builtin:
            raise ValidationAppException("内置监控对象不能删除")
        return super().destroy(request, *args, **kwargs)

    @action(methods=["get", "put"], detail=True, url_path="view_column_preference")
    def view_column_preference(self, request, pk=None):
        """读取或保存当前用户在当前监控对象下的列表列配置。"""
        monitor_object = self.get_object()
        habit_key = column_preference_habit_key(monitor_object.id)
        if request.method == "GET":
            habit = UserHabit.objects.filter(user=request.user, habit_key=habit_key).first()
            return WebUtils.response_success(self._column_preference_from_habit(habit))

        serializer = MonitorViewColumnPreferenceSerializer(data=request.data)
        if not serializer.is_valid():
            return WebUtils.response_error(
                response_data=serializer.errors,
                error_message="列配置格式无效",
            )
        field_keys = serializer.validated_data["field_keys"]
        fixed_field_keys = serializer.validated_data.get("fixed_field_keys") or []
        payload = {"field_keys": field_keys, "fixed_field_keys": fixed_field_keys}
        UserHabit.objects.update_or_create(
            user=request.user,
            habit_key=habit_key,
            defaults={"habit_value": payload},
        )
        return WebUtils.response_success(payload)

    @staticmethod
    def _column_preference_from_habit(habit):
        if habit is None or type(habit.habit_value) is not dict:
            return None
        field_keys = habit.habit_value.get("field_keys")
        if type(field_keys) is not list:
            return None
        fixed_field_keys = habit.habit_value.get("fixed_field_keys") or []
        if type(fixed_field_keys) is not list:
            fixed_field_keys = []
        return {"field_keys": field_keys, "fixed_field_keys": fixed_field_keys}

    @HasPermission("object-Add")
    def create(self, request, *args, **kwargs):
        """创建监控对象，支持同时创建子对象"""
        data = request.data
        children = data.pop("children", [])

        # 父对象自动填充 instance_id_keys
        data["instance_id_keys"] = resolve_monitor_object_instance_id_keys(
            data.get("instance_id_keys"),
            level=data.get("level", "base"),
            object_name=data.get("name", ""),
        )

        # 自动填充 default_metric
        if not data.get("default_metric"):
            data["default_metric"] = f"any({{instance_type='{data.get('name', '')}'}}) by (instance_id)"

        # 创建父对象
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        parent_obj = serializer.save()
        if {"cleanup_policy", "cleanup_timeout_days", "cleanup_timeout_value", "cleanup_timeout_unit"} & set(data):
            parent_obj = MonitorObjectCleanupPolicyService.configure(
                parent_obj,
                policy=parent_obj.cleanup_policy,
                timeout_value=parent_obj.cleanup_timeout_days,
                timeout_unit=parent_obj.cleanup_timeout_unit,
            )

        # 批量创建子对象
        if children:
            child_objects = []
            for child in children:
                if child.get("id") and child.get("name"):
                    child_objects.append(
                        MonitorObject(
                            name=child["id"],
                            display_name=child["name"],
                            icon=data.get("icon", ""),
                            type_id=data.get("type"),
                            description="",
                            level="derivative",
                            parent=parent_obj,
                            is_visible=True,
                            instance_id_keys=resolve_monitor_object_instance_id_keys(
                                [],
                                level="derivative",
                                object_name=child["id"],
                            ),
                            default_metric=f"any({{instance_type='{child['id']}'}}) by (instance_id, {child['id']})",
                        )
                    )
            if child_objects:
                MonitorObject.objects.bulk_create(child_objects)

        return WebUtils.response_success(serializer.data)

    @HasPermission("object-Edit")
    def update(self, request, *args, **kwargs):
        """更新监控对象，支持更新/新增子对象"""
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        data = request.data.copy()
        children = data.pop("children", None)
        cleanup_keys = {
            "cleanup_policy",
            "cleanup_timeout_days",
            "cleanup_timeout_value",
            "cleanup_timeout_unit",
        }
        requested_cleanup = cleanup_keys & set(data.keys())

        if instance.is_builtin:
            disallowed_keys = set(data.keys()) - cleanup_keys
            if children is not None or disallowed_keys:
                raise ValidationAppException("内置监控对象定义不可修改")
            policy = data.get("cleanup_policy", instance.cleanup_policy)
            timeout_value = data.get(
                "cleanup_timeout_value",
                data.get("cleanup_timeout_days", instance.cleanup_timeout_days),
            )
            timeout_unit = data.get("cleanup_timeout_unit", instance.cleanup_timeout_unit)
            instance = MonitorObjectCleanupPolicyService.configure(
                instance,
                policy=policy,
                timeout_value=timeout_value,
                timeout_unit=timeout_unit,
            )
            return WebUtils.response_success(self.get_serializer(instance).data)

        cleanup_policy = data.pop("cleanup_policy", instance.cleanup_policy)
        cleanup_timeout_value = data.pop(
            "cleanup_timeout_value",
            data.pop("cleanup_timeout_days", instance.cleanup_timeout_days),
        )
        cleanup_timeout_unit = data.pop("cleanup_timeout_unit", instance.cleanup_timeout_unit)

        # 父对象自动补充 instance_id_keys
        data["instance_id_keys"] = resolve_monitor_object_instance_id_keys(
            data.get("instance_id_keys", instance.instance_id_keys),
            level=data.get("level", instance.level),
            object_name=data.get("name", instance.name),
        )

        # 自动补充空的 default_metric
        if not instance.default_metric and "default_metric" not in data:
            data["default_metric"] = f"any({{instance_type='{instance.name}'}}) by (instance_id)"

        # 更新父对象；清理策略通过专用服务写入并重置累计周期。
        with transaction.atomic():
            serializer = self.get_serializer(instance, data=data, partial=partial or not data)
            serializer.is_valid(raise_exception=True)
            self.perform_update(serializer)
            if requested_cleanup:
                instance = MonitorObjectCleanupPolicyService.configure(
                    instance,
                    policy=cleanup_policy,
                    timeout_value=cleanup_timeout_value,
                    timeout_unit=cleanup_timeout_unit,
                )

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
                    new_children.append(
                        MonitorObject(
                            name=child_id,
                            display_name=child_name,
                            icon=instance.icon,
                            type_id=instance.type_id,
                            description="",
                            level="derivative",
                            parent=instance,
                            is_visible=True,
                            instance_id_keys=resolve_monitor_object_instance_id_keys(
                                [],
                                level="derivative",
                                object_name=child_id,
                            ),
                            default_metric=f"any({{instance_type='{child_id}'}}) by (instance_id, {child_id})",
                        )
                    )

            if new_children:
                MonitorObject.objects.bulk_create(new_children)

        return WebUtils.response_success(self.get_serializer(instance).data)

    @HasPermission("object-Edit")
    def partial_update(self, request, *args, **kwargs):
        return super().partial_update(request, *args, **kwargs)


class MonitorObjectTypeViewSet(viewsets.ModelViewSet):
    """监控对象类型视图"""

    queryset = MonitorObjectType.objects.all()
    serializer_class = MonitorObjectTypeSerializer
    pagination_class = None  # 不分页

    @HasPermission("object-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("object-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @HasPermission("object-Edit")
    def partial_update(self, request, *args, **kwargs):
        return super().partial_update(request, *args, **kwargs)

    @HasPermission("object-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    def list(self, request, *args, **kwargs):
        # 排除 id 为 'all' 的类型
        queryset = self.filter_queryset(self.get_queryset()).exclude(id="all")

        # 获取语言加载器
        lan = LanguageLoader(app=LanguageConstants.APP, default_lang=request.user.locale)

        # 统计每个类型下的父对象数量（不包括子对象）
        type_object_counts = MonitorObject.objects.filter(parent__isnull=True).values("type").annotate(object_count=Count("id"))
        count_map = {item["type"]: item["object_count"] for item in type_object_counts}

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
