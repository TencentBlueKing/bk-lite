import json
from datetime import datetime, timedelta, timezone

from django.db import models, transaction
from django.db.models import Count
from django_celery_beat.models import CrontabSchedule, PeriodicTask
from rest_framework import viewsets
from rest_framework.decorators import action

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.utils.current_team_scope import _normalize_organization_ids, validate_assignable_organizations
from apps.core.utils.permission_utils import (
    check_instance_permission,
    filter_instances_with_permissions,
    get_instance_permissions,
    get_permission_rules,
    get_permissions_rules,
    permission_filter,
)
from apps.core.utils.team_utils import get_current_team
from apps.core.utils.web_utils import WebUtils
from apps.log.constants.alert_policy import AlertConstants
from apps.log.constants.permission import PermissionConstants
from apps.log.filters.policy import AlertFilter, EventFilter, EventRawDataFilter, PolicyFilter
from apps.log.models.policy import Alert, Event, EventRawData, Policy, PolicyOrganization
from apps.log.serializers.policy import AlertSerializer, EventRawDataSerializer, EventSerializer, PolicySerializer
from apps.log.services.access_scope import LogAccessScopeService
from config.drf.pagination import CustomPageNumberPagination


def _to_positive_int(val, default: int, min_val: int = 1, max_val: int = 10000) -> int:
    """将查询参数安全转换为正整数，非法值返回 default。"""
    try:
        v = int(val)
    except (TypeError, ValueError):
        return default
    return max(min_val, min(v, max_val))


def get_accessible_log_policy_ids(request, collect_type_id=None):
    cache_key = "_log_accessible_policy_ids_cache"
    cached_policy_ids = getattr(request, cache_key, None)
    if cached_policy_ids is None:
        cached_policy_ids = {}
        setattr(request, cache_key, cached_policy_ids)

    normalized_collect_type_id = None if collect_type_id in (None, "", "all") else str(collect_type_id)
    if normalized_collect_type_id in cached_policy_ids:
        return cached_policy_ids[normalized_collect_type_id]

    current_team = get_current_team(request)
    if not current_team:
        cached_policy_ids[normalized_collect_type_id] = []
        return []

    include_children = request.COOKIES.get("include_children", "0") == "1"
    permissions_result = get_permissions_rules(
        request.user,
        current_team,
        "log",
        PermissionConstants.POLICY_MODULE,
        include_children=include_children,
    )
    if not isinstance(permissions_result, dict):
        permissions_result = {}

    policy_permissions = permissions_result.get("data", {})
    current_teams = permissions_result.get("team", [])
    if not policy_permissions:
        cached_policy_ids[normalized_collect_type_id] = []
        return []

    queryset = Policy.objects.select_related("collect_type").prefetch_related("policyorganization_set")
    if normalized_collect_type_id == "global":
        queryset = queryset.filter(collect_type_id__isnull=True)
    elif normalized_collect_type_id is not None:
        queryset = queryset.filter(collect_type_id=normalized_collect_type_id)

    accessible_policy_ids = []
    for policy_obj in queryset:
        teams = {org.organization for org in policy_obj.policyorganization_set.all()}
        if check_instance_permission(policy_obj.collect_type_id, policy_obj.id, teams, policy_permissions, current_teams):
            accessible_policy_ids.append(policy_obj.id)

    cached_policy_ids[normalized_collect_type_id] = accessible_policy_ids
    return accessible_policy_ids


class PolicyViewSet(viewsets.ModelViewSet):
    OPERATE_PERMISSION = "Operate"
    queryset = Policy.objects.all()
    serializer_class = PolicySerializer
    filterset_class = PolicyFilter
    pagination_class = CustomPageNumberPagination

    @staticmethod
    def _normalize_orgs(values):
        if not values:
            return set()
        if not isinstance(values, list):
            values = [values]
        organizations = set()
        for value in values:
            try:
                organizations.add(int(value))
            except (TypeError, ValueError):
                continue
        return organizations

    @staticmethod
    def _validate_organizations_payload(values, required=False):
        if values is None:
            values = []

        if not isinstance(values, list):
            return None, WebUtils.response_error(error_message="organizations must be a list")

        if required and not values:
            return None, WebUtils.response_error("organizations is required")
        if not values:
            return [], None

        try:
            normalized = sorted(_normalize_organization_ids(values))
        except BaseAppException:
            return None, WebUtils.response_error(error_message="organizations entries must be canonical positive integers")

        return normalized, None

    def _get_data_scope(self, request):
        return LogAccessScopeService.get_data_scope(request)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["data_team_ids"] = self._get_data_scope(self.request).data_team_ids
        return context

    def _refresh_response_data(self, response, instance):
        response.data = self.get_serializer(instance).data
        return response

    def _get_permission_context(self, request):
        scope = self._get_data_scope(request)
        if scope.is_superuser:
            return {"all": {"team": list(scope.data_team_ids)}}, list(scope.data_team_ids)
        permissions_result = get_permissions_rules(
            request.user,
            scope.current_team,
            "log",
            PermissionConstants.POLICY_MODULE,
            include_children=scope.include_children,
        )
        if not isinstance(permissions_result, dict):
            permissions_result = {}
        permission_data = permissions_result.get("data", {})
        if not isinstance(permission_data, dict):
            permission_data = {}
        return permission_data, list(scope.data_team_ids)

    @staticmethod
    def _policy_orgs(instance):
        return {rel.organization for rel in instance.policyorganization_set.all()}

    def _permissions_for_policy(self, instance, permission_data, current_teams):
        return get_instance_permissions(
            instance.collect_type_id,
            instance.id,
            self._policy_orgs(instance),
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

    def _authorize_policy(self, request, instance, required_permission=OPERATE_PERMISSION):
        permission_data, current_teams = self._get_permission_context(request)
        permissions = self._permissions_for_policy(instance, permission_data, current_teams)
        if required_permission not in permissions:
            return WebUtils.response_403("User does not have permission to operate this policy")
        return None

    def _authorize_target_organizations(self, request, organizations, collect_type_id=None):
        try:
            validate_assignable_organizations(request, organizations)
        except BaseAppException:
            return WebUtils.response_403("User does not have permission to assign policies to these organizations")
        return None

    def get_queryset(self):
        request = getattr(self, "request", None)
        if request is None:
            return Policy.objects.none()

        queryset, _ = self._get_accessible_policy_queryset(request)
        return queryset.select_related("collect_type").distinct()

    def _get_accessible_policy_queryset(self, request, collect_type_id=None):
        cache_key = "_policy_accessible_queryset_cache"
        cache = getattr(request, cache_key, None)
        if cache is None:
            cache = {}
            setattr(request, cache_key, cache)

        normalized_collect_type_id = None if collect_type_id in (None, "", "all") else str(collect_type_id)
        cache_field = normalized_collect_type_id if normalized_collect_type_id is not None else "__none__"
        if cache_field in cache:
            cached_ids, cached_map = cache[cache_field]
            return Policy.objects.filter(id__in=cached_ids), cached_map

        scope = self._get_data_scope(request)
        policy_permissions, current_teams = self._get_permission_context(request)
        only_global = collect_type_id == "global"

        # Apply DB-layer collect_type filtering before Python-loop to reduce rows loaded
        base_qs = (
            Policy.objects.filter(policyorganization__organization__in=list(scope.data_team_ids))
            .select_related("collect_type")
            .prefetch_related("policyorganization_set")
            .distinct()
        )
        if only_global:
            base_qs = base_qs.filter(collect_type_id__isnull=True)
        elif normalized_collect_type_id is not None:
            # 原逻辑：指定 collect_type_id 时同时保留 collect_type_id 为 NULL 的全局策略
            base_qs = base_qs.filter(models.Q(collect_type_id=normalized_collect_type_id) | models.Q(collect_type_id__isnull=True))

        accessible_instances = []
        accessible_policy_ids = []
        for policy_obj in base_qs:
            teams = {org.organization for org in policy_obj.policyorganization_set.all()}
            has_permission = scope.is_superuser or check_instance_permission(
                policy_obj.collect_type_id,
                policy_obj.id,
                teams,
                policy_permissions,
                current_teams,
            )
            if not has_permission:
                continue

            accessible_policy_ids.append(policy_obj.id)
            accessible_instances.append(
                {
                    "instance_id": policy_obj.id,
                    "organizations": list(teams),
                    "collect_type_id": policy_obj.collect_type_id,
                }
            )

        permission_map = filter_instances_with_permissions(accessible_instances, policy_permissions, current_teams)
        cache[cache_field] = (accessible_policy_ids, permission_map)
        queryset = Policy.objects.filter(id__in=accessible_policy_ids)
        return queryset, permission_map

    def list(self, request, *args, **kwargs):
        collect_type_id = request.query_params.get("collect_type") or None
        queryset, policy_permission_map = self._get_accessible_policy_queryset(request, collect_type_id)
        queryset = self.filter_queryset(queryset)
        queryset = queryset.distinct().select_related("collect_type").prefetch_related("policyorganization_set")

        # 获取分页参数
        page = _to_positive_int(request.GET.get("page"), 1)
        page_size = _to_positive_int(request.GET.get("page_size"), 10, max_val=500)

        # 计算分页的起始位置
        start = (page - 1) * page_size
        end = start + page_size

        # 获取当前页的数据
        page_data = queryset[start:end]

        # 执行序列化
        serializer = self.get_serializer(page_data, many=True)
        results = serializer.data

        # 添加权限信息到每个策略实例
        for policy_info in results:
            if policy_info["id"] in policy_permission_map:
                policy_info["permission"] = policy_permission_map[policy_info["id"]]
            else:
                policy_info["permission"] = PermissionConstants.DEFAULT_PERMISSION

        return WebUtils.response_success(dict(count=queryset.count(), items=results))

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        # 补充创建人
        request.data["created_by"] = request.user.username
        request.data["updated_by"] = request.user.username

        # 提取organizations数据，不传给serializer
        organizations, error_response = self._validate_organizations_payload(request.data.pop("organizations", []), required=True)
        if error_response:
            return error_response

        error_response = self._authorize_target_organizations(request, organizations, request.data.get("collect_type"))
        if error_response:
            return error_response

        response = super().create(request, *args, **kwargs)
        policy_id = response.data["id"]

        # 创建组织关联
        PolicyOrganization.objects.bulk_create(
            [PolicyOrganization(policy_id=policy_id, organization=org_id) for org_id in organizations],
            ignore_conflicts=True,
        )

        schedule = request.data.get("schedule")
        if schedule:
            self.update_or_create_task(policy_id, schedule)

        instance = self.get_queryset().get(id=policy_id)
        return self._refresh_response_data(response, instance)

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        error_response = self._authorize_policy(request, instance)
        if error_response:
            return error_response

        # 补充更新人
        request.data["updated_by"] = request.user.username

        # 提取organizations数据，不传给serializer
        # 注意：只有当请求中明确包含organizations时才进行更新
        organizations = None
        if "organizations" in request.data:
            organizations, error_response = self._validate_organizations_payload(request.data.pop("organizations", []))
            if error_response:
                return error_response

        effective_collect_type_id = request.data.get("collect_type", instance.collect_type_id)
        if organizations is not None:
            error_response = self._authorize_target_organizations(request, organizations, effective_collect_type_id)
            if error_response:
                return error_response

        response = super().update(request, *args, **kwargs)
        policy_id = kwargs["pk"]

        # 只有当明确传递了organizations参数时才更新组织关联
        if organizations is not None:
            # 清除旧的组织关联
            PolicyOrganization.objects.filter(policy_id=policy_id).delete()
            # 添加新的组织关联
            PolicyOrganization.objects.bulk_create(
                [PolicyOrganization(policy_id=policy_id, organization=org_id) for org_id in organizations],
                ignore_conflicts=True,
            )

        schedule = request.data.get("schedule")
        if schedule:
            self.update_or_create_task(policy_id, schedule)

        instance.refresh_from_db()
        return self._refresh_response_data(response, instance)

    @transaction.atomic
    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        error_response = self._authorize_policy(request, instance)
        if error_response:
            return error_response

        # 补充更新人
        request.data["updated_by"] = request.user.username

        # 提取organizations数据，不传给serializer
        # 注意：只有当请求中明确包含organizations时才进行更新
        organizations = None
        if "organizations" in request.data:
            organizations, error_response = self._validate_organizations_payload(request.data.pop("organizations"))
            if error_response:
                return error_response

        effective_collect_type_id = request.data.get("collect_type", instance.collect_type_id)
        if organizations is not None:
            error_response = self._authorize_target_organizations(request, organizations, effective_collect_type_id)
            if error_response:
                return error_response

        response = super().partial_update(request, *args, **kwargs)
        policy_id = kwargs["pk"]

        # 只有当明确传递了organizations参数时才更新组织关联
        if organizations is not None:
            # 清除旧的组织关联
            PolicyOrganization.objects.filter(policy_id=policy_id).delete()
            # 添加新的组织关联
            PolicyOrganization.objects.bulk_create(
                [PolicyOrganization(policy_id=policy_id, organization=org_id) for org_id in organizations],
                ignore_conflicts=True,
            )

        schedule = request.data.get("schedule")
        if schedule:
            self.update_or_create_task(policy_id, schedule)

        instance.refresh_from_db()
        return self._refresh_response_data(response, instance)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        error_response = self._authorize_policy(request, instance)
        if error_response:
            return error_response

        policy_id = kwargs["pk"]
        # 原子化：PeriodicTask 与 Policy 同事务，DB 异常时整体回滚，避免漏扫的孤儿策略 (issue #3948)
        with transaction.atomic():
            # 删除相关的定时任务
            PeriodicTask.objects.filter(name=f"log_policy_task_{policy_id}").delete()
            return super().destroy(request, *args, **kwargs)

    def format_crontab(self, schedule):
        """
        将 schedule 格式化为 CrontabSchedule 实例
        """
        from django.utils import timezone

        schedule_type = schedule.get("type")
        value = schedule.get("value")
        current_tz = timezone.get_current_timezone()

        if schedule_type == "min":
            return CrontabSchedule.objects.get_or_create(
                minute=f"*/{value}",
                hour="*",
                day_of_month="*",
                month_of_year="*",
                day_of_week="*",
                timezone=current_tz,
            )[0]
        elif schedule_type == "hour":
            return CrontabSchedule.objects.get_or_create(
                minute=0,
                hour=f"*/{value}",
                day_of_month="*",
                month_of_year="*",
                day_of_week="*",
                timezone=current_tz,
            )[0]
        elif schedule_type == "day":
            return CrontabSchedule.objects.get_or_create(
                minute=0,
                hour=0,
                day_of_month=f"*/{value}",
                month_of_year="*",
                day_of_week="*",
                timezone=current_tz,
            )[0]
        else:
            raise BaseAppException("Invalid schedule type")

    def update_or_create_task(self, policy_id, schedule):
        task_name = f"log_policy_task_{policy_id}"

        # 删除旧的定时任务
        PeriodicTask.objects.filter(name=task_name).delete()

        # 解析 schedule，并创建相应的调度
        format_crontab = self.format_crontab(schedule)
        # 创建新的 PeriodicTask
        PeriodicTask.objects.create(
            name=task_name,
            task="apps.log.tasks.policy.scan_log_policy_task",
            args=json.dumps([policy_id]),
            crontab=format_crontab,
            enabled=True,
        )

    @action(methods=["post"], detail=True, url_path="enable")
    def enable(self, request, pk=None):
        policy = self.get_object()
        error_response = self._authorize_policy(request, policy)
        if error_response:
            return error_response
        enabled = request.data.get("enabled", True)

        task_name = f"log_policy_task_{pk}"
        try:
            task = PeriodicTask.objects.get(name=task_name)
            was_enabled = task.enabled
            task.enabled = enabled
            task.save()

            if enabled and not was_enabled:
                safe_now = datetime.now(timezone.utc) - timedelta(seconds=AlertConstants.INGEST_DELAY_SECONDS)
                policy.last_run_time = safe_now
                policy.save(update_fields=["last_run_time", "updated_at"])

            return WebUtils.response_success({"enabled": enabled})
        except PeriodicTask.DoesNotExist:
            return WebUtils.response_error("策略对应的定时任务不存在")


class AlertViewSet(viewsets.ModelViewSet):
    queryset = Alert.objects.select_related("policy", "collect_type").order_by("-created_at")
    serializer_class = AlertSerializer
    filterset_class = AlertFilter
    pagination_class = CustomPageNumberPagination

    OPERATE_PERMISSION = "Operate"

    def _get_all_accessible_policy_ids(self, request):
        return get_accessible_log_policy_ids(request)

    def _authorize_alert_operate(self, request, alert):
        policy = alert.policy
        if not policy:
            return WebUtils.response_403("Alert has no associated policy")

        include_children = request.COOKIES.get("include_children", "0") == "1"
        permissions_result = get_permissions_rules(
            request.user,
            get_current_team(request),
            "log",
            PermissionConstants.POLICY_MODULE,
            include_children=include_children,
        )
        if not isinstance(permissions_result, dict):
            permissions_result = {}
        permission_data = permissions_result.get("data", {})
        current_teams = PolicyViewSet._normalize_orgs(permissions_result.get("team", []))

        policy_orgs = {rel.organization for rel in policy.policyorganization_set.all()}
        permissions = get_instance_permissions(
            policy.collect_type_id,
            policy.id,
            policy_orgs,
            permission_data,
            current_teams,
        )
        if self.OPERATE_PERMISSION not in permissions:
            return WebUtils.response_403("User does not have permission to operate this alert")
        return None

    def get_queryset(self):
        request = getattr(self, "request", None)
        if request is None:
            return Alert.objects.none()

        policy_ids = self._get_all_accessible_policy_ids(request)
        if not policy_ids:
            return Alert.objects.none()

        return (
            Alert.objects.select_related("policy", "collect_type")
            .prefetch_related("policy__policyorganization_set")
            .filter(policy_id__in=policy_ids)
            .order_by("-created_at")
        )

    def list(self, request, *args, **kwargs):
        """
        告警列表查询

        支持两种查询模式：
        1. 传入collect_type：查询特定采集类型的告警
        2. 不传collect_type：查询当前用户所有有权限的采集类型的告警
        """
        collect_type_id = request.query_params.get("collect_type", None)

        if collect_type_id:
            # 查询特定采集类型的告警
            include_children = request.COOKIES.get("include_children", "0") == "1"
            permission = get_permission_rules(
                request.user,
                get_current_team(request),
                "log",
                f"{PermissionConstants.POLICY_MODULE}.{collect_type_id}",
                include_children=include_children,
            )

            # 应用权限过滤
            policy_qs = permission_filter(
                Policy,
                permission,
                team_key="policyorganization__organization__in",
                id_key="id__in",
            )
            policy_qs = policy_qs.filter(
                collect_type_id=collect_type_id,
                policyorganization__organization=get_current_team(request),
            ).distinct()

            # 获取有权限的policy_ids
            policy_ids = list(policy_qs.values_list("id", flat=True))
        else:
            # 查询所有有权限的采集类型的告警（使用优化后的统一方法）
            policy_ids = self._get_all_accessible_policy_ids(request)

        if not policy_ids:
            return WebUtils.response_success({"count": 0, "items": []})

        # 基于policy权限过滤告警
        queryset = self.filter_queryset(self.get_queryset())
        queryset = queryset.filter(policy_id__in=policy_ids).distinct()

        # 获取分页参数
        page = _to_positive_int(request.GET.get("page"), 1)
        page_size = _to_positive_int(request.GET.get("page_size"), 10, max_val=500)

        # 计算分页
        start = (page - 1) * page_size
        end = start + page_size

        # 获取总数和当前页数据
        total_count = queryset.count()
        page_data = queryset[start:end]

        # 序列化数据
        serializer = self.get_serializer(page_data, many=True)
        results = serializer.data

        return WebUtils.response_success({"count": total_count, "items": results})

    @action(methods=["get"], detail=False, url_path="all")
    def alert_list_all(self, request):
        """
        查询当前用户所有有权限的采集类型的告警列表

        URL: /api/alerts/all/
        """
        # 使用优化后的统一方法获取策略ID和权限映射
        policy_ids = self._get_all_accessible_policy_ids(request)

        if not policy_ids:
            return WebUtils.response_success({"count": 0, "items": []})

        # 基于policy权限过滤告警
        queryset = self.filter_queryset(self.get_queryset())
        queryset = queryset.filter(policy_id__in=policy_ids).distinct()

        # 获取分页参数
        page = _to_positive_int(request.GET.get("page"), 1)
        page_size = _to_positive_int(request.GET.get("page_size"), 10, max_val=500)

        # 计算分页
        start = (page - 1) * page_size
        end = start + page_size

        # 获取总数和当前页数据
        total_count = queryset.count()
        page_data = queryset[start:end]

        # 序列化数据
        serializer = self.get_serializer(page_data, many=True)
        results = serializer.data

        return WebUtils.response_success({"count": total_count, "items": results})

    @action(methods=["post"], detail=True, url_path="closed")
    def closed(self, request, pk=None):
        alert = self.get_object()

        auth_error = self._authorize_alert_operate(request, alert)
        if auth_error:
            return auth_error

        operator = request.user.username
        alert.status = AlertConstants.STATUS_CLOSED
        alert.operator = operator
        alert.save()

        return WebUtils.response_success({"status": AlertConstants.STATUS_CLOSED, "operator": operator})

    @action(methods=["get"], detail=False, url_path="last_event")
    def get_last_event(self, request):
        """
        获取最新的事件
        """
        alert_id = request.query_params.get("alert_id")
        if not alert_id:
            return WebUtils.response_error("缺少告警ID参数")

        alert = self.get_queryset().filter(id=alert_id).first()
        if not alert:
            return WebUtils.response_error("告警不存在", status_code=404)

        event = Event.objects.filter(alert_id=alert.id, policy_id=alert.policy_id).order_by("-event_time").first()
        if not event:
            return WebUtils.response_error("未找到相关事件", status_code=404)

        event_raw_data = EventRawData.objects.filter(event_id=event.id).first()

        data = {
            "event": EventSerializer(event).data,
            "raw_data": EventRawDataSerializer(event_raw_data).data if event_raw_data else None,
        }

        return WebUtils.response_success(data)

    @action(methods=["get"], detail=False, url_path="stats")
    def stats(self, request):
        """
        告警统计接口，基于step动态分割时间区间统计

        支持两种统计模式：
        1. 传入collect_type：统计特定采集类型的告警
        2. 不传collect_type：统计当前用户所有有权限的采集类型的告警

        工作原理：
        1. 根据过滤条件获取告警数据
        2. 找到数据的最早和最晚时间
        3. 按step步长分割时间区间
        4. 统计每个区间内指定状态的告警数量
        """
        collect_type_id = request.query_params.get("collect_type", None)

        if collect_type_id:
            # 统计特定采集类型的告警
            include_children = request.COOKIES.get("include_children", "0") == "1"
            permission = get_permission_rules(
                request.user,
                get_current_team(request),
                "log",
                f"{PermissionConstants.POLICY_MODULE}.{collect_type_id}",
                include_children=include_children,
            )

            # 先过滤出有权限的Policy
            policy_qs = permission_filter(
                Policy,
                permission,
                team_key="policyorganization__organization__in",
                id_key="id__in",
            )
            policy_qs = policy_qs.filter(
                collect_type_id=collect_type_id,
                policyorganization__organization=get_current_team(request),
            ).distinct()

            # 获取有权限的policy_ids
            policy_ids = list(policy_qs.values_list("id", flat=True))
        else:
            # 统计所有有权限的采集类型的告警（使用优化后的统一方法）
            policy_ids = self._get_all_accessible_policy_ids(request)

            if not policy_ids:
                return WebUtils.response_success(
                    {
                        "total": 0,
                        "status": request.query_params.get("status", AlertConstants.STATUS_NEW),
                        "time_range": {"start": None, "end": None},
                        "step_minutes": _to_positive_int(request.query_params.get("step"), 60, min_val=1, max_val=1440),
                        "time_series": [],
                    }
                )

        # 基于policy权限过滤告警（与list接口保持一致）
        queryset = self.filter_queryset(self.get_queryset())
        queryset = queryset.filter(policy_id__in=policy_ids).distinct()

        # 获取参数
        status = request.query_params.get("status", AlertConstants.STATUS_NEW)
        step_minutes = _to_positive_int(request.query_params.get("step"), 60, min_val=1, max_val=1440)

        # 按状态过滤
        queryset = queryset.filter(status=status)

        # 默认时间窗口：最近7天
        start_time_param = request.query_params.get("start_time", "")
        end_time_param = request.query_params.get("end_time", "")
        if not start_time_param and not end_time_param:
            default_end = datetime.now(timezone.utc)
            default_start = default_end - timedelta(days=7)
            queryset = queryset.filter(created_at__gte=default_start)

        # 生成时间序列统计
        time_series_data, time_range = self._get_step_based_stats(queryset, step_minutes)

        return WebUtils.response_success(
            {
                "total": queryset.count(),
                "status": status,
                "time_range": time_range,
                "step_minutes": step_minutes,
                "time_series": time_series_data,
            }
        )

    def _get_step_based_stats(self, queryset, step_minutes):
        """基于step动态分割时间区间进行统计，按告警级别分组

        使用 DB 侧 GROUP BY 聚合替代全量物化，消除无上界内存消耗：
        先在 DB 侧按 (created_at, level) 聚合计数，得到远小于原始行数的摘要行，
        再在 Python 侧完成 bucket 归组。
        """
        time_range_data = queryset.aggregate(min_time=models.Min("created_at"), max_time=models.Max("created_at"))

        min_time = time_range_data["min_time"]
        max_time = time_range_data["max_time"]

        if not min_time or not max_time:
            return [], {"start": None, "end": None}

        time_range = {"start": min_time.isoformat(), "end": max_time.isoformat()}

        step_delta = timedelta(minutes=step_minutes)
        max_buckets = 1000
        total_span = (max_time - min_time).total_seconds()
        if step_delta.total_seconds() > 0 and total_span / step_delta.total_seconds() > max_buckets:
            step_delta = timedelta(seconds=total_span / max_buckets)

        current_time = min_time
        time_intervals = []
        while current_time <= max_time:
            interval_end = min(current_time + step_delta, max_time + timedelta(microseconds=1))
            time_intervals.append({"start": current_time, "end": interval_end})
            current_time += step_delta
            if current_time > max_time:
                break

        # DB 侧聚合：按 (created_at, level) 分组计数
        # 结果行数 = N_distinct_timestamps × N_levels（远小于原始告警行数）
        aggregated = list(queryset.values("created_at", "level").annotate(cnt=Count("id")).order_by("created_at"))

        interval_results = []
        agg_idx = 0
        for interval in time_intervals:
            level_data = {}
            while agg_idx < len(aggregated) and aggregated[agg_idx]["created_at"] < interval["end"]:
                if aggregated[agg_idx]["created_at"] >= interval["start"]:
                    level = aggregated[agg_idx]["level"]
                    level_data[level] = level_data.get(level, 0) + aggregated[agg_idx]["cnt"]
                agg_idx += 1

            total_count = sum(level_data.values())
            interval_results.append(
                {
                    "time_start": interval["start"].isoformat(),
                    "time_end": interval["end"].isoformat(),
                    "total": total_count,
                    "levels": level_data,
                }
            )

        return interval_results, time_range

    @action(methods=["get"], detail=False, url_path="snapshots/(?P<alert_id>[^/.]+)")
    def get_snapshots(self, request, alert_id):
        """根据告警ID查询快照数据

        Args:
            alert_id: 告警ID

        Returns:
            {
                "alert_info": {
                    "id": "xxx",
                    "policy_id": 123,
                    "source_id": "policy_123",
                    "status": "new",
                    "level": "error",
                    "start_event_time": "2025-11-19T...",
                    "end_event_time": "2025-11-19T...",
                },
                "snapshots": [
                    {
                        "type": "event",
                        "event_id": "xxx",
                        "event_time": "2025-11-19T...",
                        "snapshot_time": "2025-11-19T...",
                        "raw_data": {...}
                    },
                    ...
                ]
            }
        """
        from apps.core.logger import logger
        from apps.log.models.policy import AlertSnapshot

        try:
            alert_obj = self.get_queryset().get(id=alert_id)
        except Alert.DoesNotExist:
            return WebUtils.response_error("告警不存在", status_code=404)
        except Exception as e:
            logger.error(f"Permission check failed for alert {alert_id}: {e}")
            return WebUtils.response_error("权限校验失败", status_code=403)

        # 3. 查询该告警的快照记录
        try:
            snapshot_obj = AlertSnapshot.objects.get(alert_id=alert_obj.id)
        except AlertSnapshot.DoesNotExist:
            # 快照不存在，返回空快照列表
            return WebUtils.response_success(
                {
                    "alert_info": {
                        "id": alert_obj.id,
                        "policy_id": alert_obj.policy_id,
                        "source_id": alert_obj.source_id,
                        "status": alert_obj.status,
                        "level": alert_obj.level,
                        "content": alert_obj.content,
                        "start_event_time": alert_obj.start_event_time,
                        "end_event_time": alert_obj.end_event_time,
                    },
                    "snapshots": [],
                }
            )

        # 4. 从 S3 加载快照数据（S3JSONField 自动处理）
        try:
            snapshots_data = snapshot_obj.snapshots  # 自动从 S3 下载并解析
            # 如果 S3 加载失败返回 None，使用空列表
            if snapshots_data is None:
                snapshots_data = []
        except Exception as e:
            # S3 读取异常时记录日志并返回空列表
            logger.error(f"Failed to load snapshots from S3 for alert {alert_id}: {e}")
            snapshots_data = []

        # 5. 返回快照数据
        return WebUtils.response_success(
            {
                "alert_info": {
                    "id": alert_obj.id,
                    "policy_id": alert_obj.policy_id,
                    "source_id": alert_obj.source_id,
                    "status": alert_obj.status,
                    "level": alert_obj.level,
                    "content": alert_obj.content,
                    "value": alert_obj.value,
                    "start_event_time": alert_obj.start_event_time,
                    "end_event_time": alert_obj.end_event_time,
                    "created_at": alert_obj.created_at,
                    "updated_at": alert_obj.updated_at,
                },
                "snapshot_info": {
                    "snapshot_count": len(snapshots_data),
                    "created_at": snapshot_obj.created_at,
                    "updated_at": snapshot_obj.updated_at,
                },
                "snapshots": snapshots_data,
            }
        )


class EventViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Event.objects.all()
    serializer_class = EventSerializer
    filterset_class = EventFilter
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        request = getattr(self, "request", None)
        if request is None:
            return Event.objects.none()

        policy_ids = get_accessible_log_policy_ids(request)
        if not policy_ids:
            return Event.objects.none()

        return Event.objects.select_related("policy", "alert").filter(policy_id__in=policy_ids).order_by("-event_time")


class EventRawDataViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = EventRawData.objects.all()
    serializer_class = EventRawDataSerializer
    filterset_class = EventRawDataFilter
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        request = getattr(self, "request", None)
        if request is None:
            return EventRawData.objects.none()

        policy_ids = get_accessible_log_policy_ids(request)
        if not policy_ids:
            return EventRawData.objects.none()

        return EventRawData.objects.select_related("event").filter(event__policy_id__in=policy_ids).order_by("-event__event_time", "-id")

    @action(methods=["get"], detail=False, url_path="by_event_id")
    def rawdata_list_by_event_id(self, request):
        """
        根据事件ID获取原始数据

        由于每个事件只对应一条原始数据记录，所以直接返回对应的数据，无需分页

        URL: /api/event-raw-data/by_event_id/?event_id=xxx
        """
        event_id = request.query_params.get("event_id")
        if not event_id:
            return WebUtils.response_error("缺少事件ID参数")

        try:
            # 直接获取对应的原始数据记录
            event_raw_data = self.get_queryset().get(event_id=event_id)
            serializer = self.get_serializer(event_raw_data)
            return WebUtils.response_success(serializer.data)
        except EventRawData.DoesNotExist:
            return WebUtils.response_error("未找到对应的原始数据", status_code=404)
