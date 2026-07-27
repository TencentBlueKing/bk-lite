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
from apps.monitor.filters.monitor_alert import MonitorAlertFilter
from apps.monitor.models import MonitorAlert, MonitorAlertMetricSnapshot, MonitorEvent, MonitorEventRawData, MonitorPolicy, PolicyInstanceBaseline
from apps.monitor.serializers.monitor_alert import MonitorAlertSerializer, MonitorAlertUpdateSerializer
from apps.monitor.serializers.monitor_policy import MonitorPolicySerializer
from apps.monitor.services.alert_lifecycle_notify import AlertLifecycleNotifier
from apps.monitor.services.chart_unit import convert_snapshots_copy, resolve_chart_unit
from apps.monitor.services.policy_baseline import PolicyBaselineService
from apps.monitor.utils.dimension import parse_instance_id
from apps.monitor.utils.pagination import parse_page_params
from config.drf.pagination import CustomPageNumberPagination


class AlertPermissionMixin:
    """
    共享的策略权限过滤逻辑。

    将原先在 MonitorAlertViewSet 和 MonitorEventViewSet 中各自重复定义的
    _get_all_accessible_policy_ids / _check_alert_permission 提取到此 Mixin，
    同时将全量加载改为按权限数据结构预先缩小 DB 查询范围，避免 O(N) 全表扫描。
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
            MonitorPolicy.objects.filter(
                policyorganization__organization__in=list(scope.data_team_ids)
            )
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
            known_object_type_ids = [
                int(k) for k in policy_permissions.keys() if k != "all" and str(k).isdigit()
            ]
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
        accessible_policy_ids = self._get_all_accessible_policy_ids(request)
        return alert_obj.policy_id in accessible_policy_ids


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
        """所有入口均从受限策略根派生告警 queryset。"""
        qs = super().get_queryset()
        request = self.request
        require_operate = self.action in ("update", "partial_update")
        policy_qs = self.get_accessible_policy_queryset(
            request,
            require_operate=require_operate,
        )
        return qs.filter(policy_id__in=policy_qs.values("id"))

    def list(self, request, *args, **kwargs):
        monitor_object_id = request.query_params.get("monitor_object_id", None)
        policy_qs = self.get_accessible_policy_queryset(request)
        if monitor_object_id:
            policy_qs = policy_qs.filter(monitor_object_id=monitor_object_id)
        policy_ids = policy_qs.values_list("id", flat=True)

        if not policy_ids:
            return WebUtils.response_success(dict(count=0, results=[]))

        # 获取经过过滤器处理的数据
        queryset = self.filter_queryset(self.get_queryset())
        queryset = queryset.filter(policy_id__in=list(policy_ids)).distinct()

        if request.GET.get("type") == "count":
            # 执行序列化
            serializer = self.get_serializer(queryset, many=True)
            # 返回成功响应
            return WebUtils.response_success(dict(count=queryset.count(), results=serializer.data))

        # 获取分页参数
        page, page_size = parse_page_params(request.GET, default_page=1, default_page_size=10)

        # 计算分页的起始位置
        start = (page - 1) * page_size
        end = start + page_size

        # 获取当前页的数据
        page_data = queryset[start:end]

        # 执行序列化
        serializer = self.get_serializer(page_data, many=True)
        results = serializer.data

        # 获取当前页中所有的 policy_id 和 monitor_instance_id
        _policy_ids = [alert["policy_id"] for alert in results if alert["policy_id"]]

        # 查询所有相关的策略和实例
        policies = policy_qs.filter(id__in=_policy_ids)

        # 将策略和实例数据映射到字典中
        policy_dict = {policy.id: policy for policy in policies}

        # # 如果有权限规则，则添加到数据中
        # inst_permission_map = {i["id"]: i["permission"] for i in permission.get("instance", [])}

        # 补充策略和实例到每个 alert 中

        for alert in results:
            # # 补充权限信息
            # if alert["policy_id"] in inst_permission_map:
            #     alert["permission"] = inst_permission_map[alert["policy_id"]]
            # else:
            #     alert["permission"] = DEFAULT_PERMISSION

            # 补充instance_id_values

            alert["instance_id_values"] = list(parse_instance_id(alert["monitor_instance_id"]))
            # 在 results 字典中添加完整的 policy 和 monitor_instance 信息
            alert["policy"] = (
                MonitorPolicySerializer(
                    policy_dict.get(alert["policy_id"]),
                    context={"data_team_ids": self._get_data_scope(request).data_team_ids},
                ).data
                if alert["policy_id"]
                else None
            )

        # 返回成功响应
        return WebUtils.response_success(dict(count=queryset.count(), results=results))

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
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
                with transaction.atomic():
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
        else:
            self.perform_update(serializer)
        instance.refresh_from_db()

        if old_status == "new" and instance.status == "closed":
            policy = MonitorPolicy.objects.filter(id=instance.policy_id).first()
            if policy:
                AlertLifecycleNotifier(policy).notify_alerts(
                    [instance],
                    action="closed",
                    operator=request.user.username,
                    reason="manual",
                )

        if getattr(instance, "_prefetched_objects_cache", None):
            instance._prefetched_objects_cache = {}

        return Response(serializer.data)

    @action(methods=["get"], detail=False, url_path="snapshots/(?P<alert_id>[^/.]+)")
    def get_snapshots(self, request, alert_id):
        """根据告警ID查询指标快照数据"""
        alert_obj = self.get_queryset().filter(id=alert_id).first()
        if alert_obj is None:
            return WebUtils.response_error("告警不存在", status_code=404)

        policy_units = (
            MonitorPolicy.objects.filter(id=alert_obj.policy_id)
            .values("metric_unit", "calculation_unit", "threshold_unit")
            .first()
            or {}
        )
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

        accessible_policy_qs = self.get_accessible_policy_queryset(request)
        alert_obj = MonitorAlert.objects.filter(
            id=alert_id,
            policy_id__in=accessible_policy_qs.values("id"),
        ).first()
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
        accessible_policy_qs = self.get_accessible_policy_queryset(request)
        event_obj = (
            MonitorEvent.objects.filter(
                id=event_id,
                policy_id__in=accessible_policy_qs.values("id"),
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
