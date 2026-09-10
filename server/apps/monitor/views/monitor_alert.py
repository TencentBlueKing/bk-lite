from datetime import datetime, timezone

from django.db import transaction
from django.db.models import F, Q
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.core.logger import monitor_logger as logger
from apps.core.utils.current_team_scope import resolve_current_team_data_scope
from apps.core.utils.permission_utils import get_instance_permissions, get_permissions_rules
from apps.core.utils.web_utils import WebUtils
from apps.monitor.constants.permission import PermissionConstants
from apps.monitor.filters.id_filters import filter_positive_int_field
from apps.monitor.filters.monitor_alert import MonitorAlertFilter
from apps.monitor.models import MonitorAlert, MonitorAlertMetricSnapshot, MonitorEvent, MonitorEventRawData, MonitorPolicy, PolicyInstanceBaseline
from apps.monitor.serializers.monitor_alert import (
    AssignHandlersSerializer,
    MonitorAlertSerializer,
    MonitorAlertUpdateSerializer,
)
from apps.monitor.services.alert_handlers import (
    AlertHandlerConflict,
    AlertHandlerForbidden,
    AlertHandlerInvalid,
    assign_alert,
    claim_alert,
    filter_my_handler_alerts,
    is_my_alert_query,
)
from apps.monitor.serializers.monitor_policy import MonitorPolicySerializer
from apps.monitor.services.alert_access import visible_monitor_alerts
from apps.monitor.services.alert_lifecycle_events import record_lifecycle_events
from apps.monitor.services.alert_lifecycle_notify import AlertLifecycleNotifier
from apps.monitor.services.chart_unit import convert_snapshots_copy, resolve_chart_unit
from apps.monitor.services.policy_baseline import PolicyBaselineService
from apps.monitor.utils.dimension import parse_instance_id
from apps.monitor.utils.pagination import parse_page_params
from apps.monitor.utils.user_display import (
    enrich_alerts_handlers_display,
    enrich_alerts_notice_users_display,
)
from config.drf.pagination import CustomPageNumberPagination


class AlertPermissionMixin:
    """
    共享的告警可见性与策略权限。

    告警列表/详情按生成时组织快照 fail-closed；策略对象级权限仍用于策略本身
    以及未删除策略上的实例授权。策略删除后，告警仍可按快照组织查看。
    """

    def _get_data_scope(self, request):
        if not hasattr(self, "_current_team_data_scope"):
            self._current_team_data_scope = resolve_current_team_data_scope(request)
        return self._current_team_data_scope

    def get_accessible_policy_queryset(self, request, require_operate=False):
        """
        返回对象权限与 current_team 数据范围交集内的策略 queryset。

        超级管理员仅绕过功能动作授权，不绕过 current_team 数据范围。普通
        用户继续按既有对象权限判断；require_operate=True 时只保留具备
        Operate 权限的实例授权。
        """
        scope = self._get_data_scope(request)
        policy_qs = (
            MonitorPolicy.objects.filter(policyorganization__organization__in=list(scope.data_team_ids))
            .select_related("monitor_object")
            .prefetch_related("policyorganization_set")
            .distinct()
        )

        if request.user.is_superuser:
            return policy_qs

        permissions_result = get_permissions_rules(
            request.user,
            scope.current_team,
            "monitor",
            PermissionConstants.POLICY_MODULE,
            include_children=scope.include_children,
        )

        if not isinstance(permissions_result, dict):
            return policy_qs.none()
        policy_permissions = permissions_result.get("data", {})
        cur_team = permissions_result.get("team", [])

        if not isinstance(policy_permissions, dict) or not isinstance(cur_team, list):
            return policy_qs.none()

        # 从权限数据中提取已知的 monitor_object_id，用于 DB 层预过滤。
        # policy_permissions 结构：{ object_type_id: {instance: [...], team: [...]}, "all": {...} }
        # "all" 键表示管理员级别权限（对全部对象类型生效），此时不能缩小范围。
        if "all" not in policy_permissions:
            known_object_type_ids = [int(k) for k in policy_permissions.keys() if k != "all" and str(k).isdigit()]
            policy_qs = policy_qs.filter(monitor_object_id__in=known_object_type_ids)

        accessible_policy_ids = []
        for policy_obj in policy_qs:
            monitor_object_id = str(policy_obj.monitor_object_id)
            policy_id = policy_obj.id
            teams = {org.organization for org in policy_obj.policyorganization_set.all()}
            permissions = get_instance_permissions(
                monitor_object_id,
                policy_id,
                teams,
                policy_permissions,
                cur_team,
            )
            if permissions and (not require_operate or "Operate" in permissions):
                accessible_policy_ids.append(policy_id)

        return policy_qs.filter(id__in=accessible_policy_ids)

    def get_visible_alert_queryset(self, request, require_operate=False):
        """告警可见性以生成时组织快照为准，不再跟随策略当前组织。"""
        scope = self._get_data_scope(request)
        permissions_data = None
        if not request.user.is_superuser:
            permissions_result = get_permissions_rules(
                request.user,
                scope.current_team,
                "monitor",
                PermissionConstants.POLICY_MODULE,
                include_children=scope.include_children,
            )
            permissions_data = permissions_result.get("data") if isinstance(permissions_result, dict) else None
        return visible_monitor_alerts(
            MonitorAlert.objects.all(),
            organization_ids=list(scope.data_team_ids),
            is_superuser=request.user.is_superuser,
            permissions_data=permissions_data,
            require_operate=require_operate,
        )

    def _get_all_accessible_policy_ids(self, request, require_operate=False):
        """兼容既有调用方，ID 集合始终由受限策略根 queryset 派生。"""
        return list(
            self.get_accessible_policy_queryset(
                request,
                require_operate=require_operate,
            ).values_list("id", flat=True)
        )

    def _check_alert_permission(self, request, alert_obj):
        """Check if the current user has permission to access the given alert."""
        return self.get_visible_alert_queryset(request).filter(pk=alert_obj.pk).exists()

    def _build_policy_permission_map(self, request, policies):
        """为告警列表补充每条策略的实例权限，供前端编辑按钮门控。"""
        if not policies:
            return {}

        if request.user.is_superuser:
            return {policy.id: PermissionConstants.DEFAULT_PERMISSION for policy in policies}

        scope = self._get_data_scope(request)
        permissions_result = get_permissions_rules(
            request.user,
            scope.current_team,
            "monitor",
            PermissionConstants.POLICY_MODULE,
            include_children=scope.include_children,
        )
        if not isinstance(permissions_result, dict):
            return {}

        policy_permissions = permissions_result.get("data", {})
        cur_team = permissions_result.get("team", [])
        if not isinstance(policy_permissions, dict) or not isinstance(cur_team, list):
            return {}

        permission_map = {}
        for policy_obj in policies:
            monitor_object_id = str(policy_obj.monitor_object_id)
            teams = {org.organization for org in policy_obj.policyorganization_set.all()}
            permissions = get_instance_permissions(
                monitor_object_id,
                policy_obj.id,
                teams,
                policy_permissions,
                cur_team,
            )
            permission_map[policy_obj.id] = permissions
        return permission_map


class MonitorAlertViewSet(
    AlertPermissionMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    GenericViewSet,
):
    queryset = MonitorAlert.objects.all().order_by("-created_at")
    serializer_class = MonitorAlertSerializer
    filterset_class = MonitorAlertFilter
    pagination_class = CustomPageNumberPagination

    def get_serializer_class(self):
        if self.action in ("update", "partial_update"):
            return MonitorAlertUpdateSerializer
        return super().get_serializer_class()

    def get_queryset(self):
        """所有入口均从告警组织快照派生可见集合。"""
        request = self.request
        require_operate = self.action in ("update", "partial_update")
        return self.get_visible_alert_queryset(
            request,
            require_operate=require_operate,
        ).order_by("-created_at")

    def list(self, request, *args, **kwargs):
        monitor_object_id = request.query_params.get("monitor_object_id", None)
        queryset = self.filter_queryset(self.get_queryset())
        if is_my_alert_query(request):
            queryset = filter_my_handler_alerts(queryset, request.user)
        if monitor_object_id not in (None, ""):
            policy_qs = filter_positive_int_field(
                MonitorPolicy.objects.all(),
                "monitor_object_id",
                monitor_object_id,
            )
            queryset = queryset.filter(policy_id__in=policy_qs.values("id"))

        if request.GET.get("type") == "count":
            serializer = self.get_serializer(queryset, many=True)
            return WebUtils.response_success(dict(count=queryset.count(), results=serializer.data))

        page, page_size = parse_page_params(request.GET, default_page=1, default_page_size=10)
        start = (page - 1) * page_size
        end = start + page_size
        page_data = queryset[start:end]
        serializer = self.get_serializer(page_data, many=True)
        results = serializer.data

        _policy_ids = [alert["policy_id"] for alert in results if alert["policy_id"]]
        policies = list(MonitorPolicy.objects.filter(id__in=_policy_ids).prefetch_related("policyorganization_set"))
        policy_dict = {policy.id: policy for policy in policies}
        policy_permission_map = self._build_policy_permission_map(request, policies)
        data_team_ids = self._get_data_scope(request).data_team_ids

        for alert in results:
            policy_id = alert["policy_id"]
            policy_obj = policy_dict.get(policy_id)
            if policy_id in policy_permission_map:
                alert["policy_permission"] = policy_permission_map[policy_id]
            elif policy_obj:
                alert["policy_permission"] = PermissionConstants.DEFAULT_PERMISSION
            else:
                alert["policy_permission"] = []

            alert["instance_id_values"] = list(parse_instance_id(alert["monitor_instance_id"]))
            alert["policy"] = (
                MonitorPolicySerializer(
                    policy_obj,
                    context={
                        "data_team_ids": data_team_ids,
                        "filter_organizations": True,
                    },
                ).data
                if policy_obj
                else None
            )

        enrich_alerts_notice_users_display(results)
        enrich_alerts_handlers_display(results)
        return WebUtils.response_success(dict(count=queryset.count(), results=results))

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        authorized_instance = self.get_object()

        with transaction.atomic():
            # 权限范围先由 get_object 校验；状态转换必须锁内重读，避免扫描任务与
            # 两个手工关闭请求都基于同一个旧 new 状态重复落 lifecycle intent。
            instance = MonitorAlert.objects.select_for_update().get(pk=authorized_instance.pk)
            # 锁等待期间组织关系、角色或策略归属都可能变化；始终以锁内时刻
            # 重新走权限过滤，禁止复用过期授权依据。
            instance = self.get_queryset().get(pk=instance.pk)
            old_status = instance.status
            serializer = self.get_serializer(instance, data=request.data, partial=partial)
            serializer.is_valid(raise_exception=True)
            updated_data = serializer.validated_data
            if updated_data.get("status") == "closed":
                now = datetime.now(timezone.utc)
                updated_data["end_event_time"] = now
                updated_data["operator"] = request.user.username
                updated_data["operation_logs"] = (instance.operation_logs or []) + [
                    {
                        "action": "closed",
                        "reason": "manual",
                        "operator": request.user.username,
                        "time": now.isoformat(),
                    }
                ]
                # 只有 new → closed 的转换才需要补偿推送，避免重复关闭触发多余的告警中心推送
                if old_status == "new":
                    updated_data["alert_center_notified"] = False

                # 基线清理/刷新 与 告警 status 写库 必须在同一事务中。
                # 否则 perform_update 失败时 baseline 已删/已刷,下次扫描会再次 new 一条
                # 一模一样的 no_data 告警，相当于「用户手动关了又自动重开」(issue #4041)。
                # 注意:refresh() 内部含 VM scan,事务不宜过长——失败 → 整段回滚即满足需求。
                if instance.alert_type == "no_data" and instance.metric_instance_id:
                    update_baseline = request.data.get("update_baseline", False)
                    if update_baseline:
                        policy = MonitorPolicy.objects.filter(id=instance.policy_id).first()
                        if policy:
                            PolicyBaselineService(policy).refresh()
                    else:
                        PolicyInstanceBaseline.objects.filter(
                            policy_id=instance.policy_id,
                            metric_instance_id=instance.metric_instance_id,
                        ).delete()
                    self.perform_update(serializer)
                else:
                    self.perform_update(serializer)
                if old_status == "new":
                    instance.refresh_from_db()
                    record_lifecycle_events(
                        [instance],
                        MonitorEvent.Action.CLOSED,
                        event_time=now,
                        operator=request.user.username,
                        reason="manual",
                    )
            else:
                self.perform_update(serializer)
            instance.refresh_from_db()

            if old_status == "new" and instance.status == "closed":
                policy = MonitorPolicy.objects.filter(id=instance.policy_id).first()
                if policy:
                    notifier = AlertLifecycleNotifier(policy)
                    notifier.enqueue_alert_center_deliveries(
                        [instance],
                        "closed",
                        operator=request.user.username,
                        reason="manual",
                    )
                    transaction.on_commit(
                        lambda: notifier.notify_alerts(
                            [instance],
                            action="closed",
                            operator=request.user.username,
                            reason="manual",
                        )
                    )

        if getattr(instance, "_prefetched_objects_cache", None):
            instance._prefetched_objects_cache = {}

        return Response(serializer.data)

    def _authorize_alert_operate(self, request, alert):
        if not self.get_visible_alert_queryset(request, require_operate=True).filter(pk=alert.pk).exists():
            return WebUtils.response_403("没有操作该告警的权限")
        return None

    def retrieve(self, request, *args, **kwargs):
        return self._handler_action_response(self.get_object())

    def _handler_action_response(self, alert):
        data = MonitorAlertSerializer(alert).data
        enrich_alerts_notice_users_display([data])
        enrich_alerts_handlers_display([data])
        return Response(data)

    @action(methods=["post"], detail=True, url_path="claim")
    def claim(self, request, pk=None):
        alert = self.get_object()
        auth_error = self._authorize_alert_operate(request, alert)
        if auth_error:
            return auth_error
        operable_qs = self.get_visible_alert_queryset(request, require_operate=True)
        try:
            updated = claim_alert(alert, actor=request.user, operable_qs=operable_qs)
        except AlertHandlerForbidden as exc:
            return WebUtils.response_403(str(exc))
        except AlertHandlerConflict as exc:
            return WebUtils.response_error(str(exc), status_code=409)
        return self._handler_action_response(updated)

    @action(methods=["post"], detail=True, url_path="assign")
    def assign(self, request, pk=None):
        alert = self.get_object()
        auth_error = self._authorize_alert_operate(request, alert)
        if auth_error:
            return auth_error
        serializer = AssignHandlersSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        operable_qs = self.get_visible_alert_queryset(request, require_operate=True)
        try:
            updated = assign_alert(
                alert,
                handlers=serializer.validated_data["handlers"],
                actor=request.user,
                operable_qs=operable_qs,
            )
        except AlertHandlerForbidden as exc:
            return WebUtils.response_403(str(exc))
        except AlertHandlerInvalid as exc:
            return WebUtils.response_error(str(exc), status_code=400)
        except AlertHandlerConflict as exc:
            return WebUtils.response_error(str(exc), status_code=409)
        return self._handler_action_response(updated)

    @action(methods=["get"], detail=False, url_path="snapshots/(?P<alert_id>[^/.]+)")
    def get_snapshots(self, request, alert_id):
        """根据告警ID查询指标快照数据"""
        alert_obj = self.get_queryset().filter(id=alert_id).first()
        if alert_obj is None:
            return WebUtils.response_error("告警不存在", status_code=404)

        policy_units = MonitorPolicy.objects.filter(id=alert_obj.policy_id).values("metric_unit", "calculation_unit", "threshold_unit").first() or {}
        metric_unit = policy_units.get("metric_unit") or ""
        calculation_unit = policy_units.get("calculation_unit") or ""
        threshold_unit = policy_units.get("threshold_unit") or ""
        source_unit = calculation_unit or metric_unit
        chart_unit = resolve_chart_unit(
            metric_unit,
            calculation_unit,
            threshold_unit,
        )

        # 2. 查询该告警的快照记录
        try:
            snapshot_obj = MonitorAlertMetricSnapshot.objects.get(
                alert_id=alert_obj.id,
                policy_id=alert_obj.policy_id,
            )
        except MonitorAlertMetricSnapshot.DoesNotExist:
            if MonitorAlertMetricSnapshot.objects.filter(alert_id=alert_obj.id).exists():
                return WebUtils.response_error("告警快照不存在", status_code=404)
            return WebUtils.response_success(
                {
                    "alert_info": {
                        "id": alert_obj.id,
                        "policy_id": alert_obj.policy_id,
                        "monitor_instance_id": alert_obj.monitor_instance_id,
                        "status": alert_obj.status,
                        "start_event_time": alert_obj.start_event_time,
                        "end_event_time": alert_obj.end_event_time,
                    },
                    "chart_unit": chart_unit,
                    "snapshots": [],
                }
            )

        # 3. 从 S3 加载快照数据（S3JSONField 自动处理）
        try:
            snapshots_data = snapshot_obj.snapshots  # 自动从 S3 下载并解析
            # 如果 S3 加载失败返回 None，使用空列表
            if snapshots_data is None:
                snapshots_data = []
        except Exception as e:
            # S3 读取异常时记录日志并返回空列表
            logger.error(f"Failed to load snapshots from S3 for alert {alert_id}: {e}")
            snapshots_data = []

        snapshots_data = convert_snapshots_copy(
            snapshots_data,
            source_unit or chart_unit,
            chart_unit,
        )

        # 4. 返回快照数据
        return WebUtils.response_success(
            {
                "alert_info": {
                    "id": alert_obj.id,
                    "policy_id": alert_obj.policy_id,
                    "monitor_instance_id": alert_obj.monitor_instance_id,
                    "status": alert_obj.status,
                    "start_event_time": alert_obj.start_event_time,
                    "end_event_time": alert_obj.end_event_time,
                },
                "chart_unit": chart_unit,
                "snapshots": snapshots_data,
            }
        )


class MonitorEventViewSet(AlertPermissionMixin, viewsets.ViewSet):
    @action(methods=["get"], detail=False, url_path="query/(?P<alert_id>[^/.]+)")
    def get_events(self, request, alert_id):
        """查询告警的事件列表 - 优化版：使用外键直接查询"""
        page, page_size = parse_page_params(
            request.GET,
            default_page=1,
            default_page_size=10,
            allow_page_size_all=True,
        )

        accessible_alerts = self.get_visible_alert_queryset(request)
        alert_obj = accessible_alerts.filter(id=alert_id).first()
        if alert_obj is None:
            return WebUtils.response_error("告警不存在", status_code=404)

        # ✅ 优化：直接通过 alert_id 外键查询，性能更优
        linked_events = MonitorEvent.objects.filter(alert_id=alert_id)
        q_set = linked_events.filter(policy_id=alert_obj.policy_id).order_by("-created_at")

        # 如果没有通过外键查询到数据，降级到组合条件查询（兼容历史数据）
        if not linked_events.exists():
            event_query = dict(
                policy_id=alert_obj.policy_id,
                monitor_instance_id=alert_obj.monitor_instance_id,
                created_at__gte=alert_obj.start_event_time,
            )
            if alert_obj.end_event_time:
                event_query["created_at__lte"] = alert_obj.end_event_time
            q_set = MonitorEvent.objects.filter(**event_query).order_by("-created_at")

        if page_size == -1:
            events = q_set
        else:
            events = q_set[(page - 1) * page_size : page * page_size]

        result = [
            {
                "id": i.id,
                "level": i.level,
                "value": i.value,
                "content": i.content,
                "action": i.action or "",
                "created_at": i.created_at,
                "monitor_instance_id": i.monitor_instance_id,
                "policy_id": i.policy_id,
                "event_time": i.event_time,
            }
            for i in events
        ]
        return WebUtils.response_success(dict(count=q_set.count(), results=result))

    @action(methods=["get"], detail=False, url_path="raw_data/(?P<event_id>[^/.]+)")
    def get_raw_data(self, request, event_id):
        """根据事件ID获取事件的原始指标数据（从 S3 加载）"""
        accessible_alerts = self.get_visible_alert_queryset(request)
        accessible_policy_qs = self.get_accessible_policy_queryset(request)
        event_obj = (
            MonitorEvent.objects.filter(id=event_id)
            .filter(
                Q(alert_id__in=accessible_alerts.values("id"))
                | Q(alert__isnull=True, policy_id__in=accessible_policy_qs.values("id"))
            )
            .filter(Q(alert__isnull=True) | Q(alert__policy_id=F("policy_id")))
            .first()
        )
        if event_obj is None:
            return WebUtils.response_error("事件不存在", status_code=404)

        # 2. 查询该事件的原始数据
        raw_data_obj = MonitorEventRawData.objects.filter(event_id=event_obj.id).first()

        if not raw_data_obj:
            return WebUtils.response_success({})

        # 3. 从 S3 加载原始数据（S3JSONField 自动处理）
        try:
            raw_data = raw_data_obj.data  # 自动从 S3 下载并解析
            # 如果 S3 加载失败返回 None，使用空字典
            if raw_data is None:
                raw_data = {}
        except Exception as e:
            # S3 读取异常时记录日志并返回空字典
            logger.error(f"Failed to load raw data from S3 for event {event_id}: {e}")
            raw_data = {}

        return WebUtils.response_success(raw_data)
