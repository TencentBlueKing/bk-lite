import ast
from datetime import datetime, timezone

from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import viewsets, mixins
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.core.utils.permission_utils import get_permission_rules, permission_filter
from apps.core.utils.web_utils import WebUtils
from apps.monitor.constants import DEFAULT_PERMISSION, POLICY_MODULE
from apps.monitor.models import MonitorAlert, MonitorEvent, MonitorPolicy, MonitorEventRawData
from apps.monitor.models.monitor_policy import MonitorAlertMetricSnapshot
from apps.monitor.filters.monitor_alert import MonitorAlertFilter
from apps.monitor.serializers.monitor_alert import MonitorAlertSerializer, MonitorAlertMetricSnapshotSerializer
from apps.monitor.serializers.monitor_policy import MonitorPolicySerializer
from config.drf.pagination import CustomPageNumberPagination


class MonitorAlertVieSet(
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    GenericViewSet
):
    queryset = MonitorAlert.objects.all().order_by("-created_at")
    serializer_class = MonitorAlertSerializer
    filterset_class = MonitorAlertFilter
    pagination_class = CustomPageNumberPagination

    def list(self, request, *args, **kwargs):
        monitor_object_id = request.query_params.get('monitor_object_id', None)
        if not monitor_object_id:
            return WebUtils.response_error("monitor_object_id is required")
        permission = get_permission_rules(
            request.user,
            request.COOKIES.get("current_team"),
            "monitor",
            f"{POLICY_MODULE}.{monitor_object_id}",
        )
        qs = permission_filter(MonitorPolicy, permission, team_key="policyorganization__organization__in", id_key="id__in")

        qs = qs.filter(monitor_object_id=monitor_object_id).distinct()
        policy_ids = qs.values_list("id", flat=True)

        # 获取经过过滤器处理的数据
        queryset = self.filter_queryset(self.get_queryset())
        queryset = queryset.filter(policy_id__in=list(policy_ids)).distinct()

        if request.GET.get("type") == "count":
            # 执行序列化
            serializer = self.get_serializer(queryset, many=True)
            # 返回成功响应
            return WebUtils.response_success(dict(count=queryset.count(), results=serializer.data))

        # 获取分页参数
        page = int(request.GET.get('page', 1))  # 默认第1页
        page_size = int(request.GET.get('page_size', 10))  # 默认每页10条数据

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
        policies = MonitorPolicy.objects.filter(id__in=_policy_ids)

        # 将策略和实例数据映射到字典中
        policy_dict = {policy.id: policy for policy in policies}

        # 如果有权限规则，则添加到数据中
        inst_permission_map = {i["id"]: i["permission"] for i in permission.get("instance", [])}

        # 补充策略和实例到每个 alert 中
        for alert in results:

            # 补充权限信息
            if alert["policy_id"] in inst_permission_map:
                alert["permission"] = inst_permission_map[alert["policy_id"]]
            else:
                alert["permission"] = DEFAULT_PERMISSION

            # 补充instance_id_values
            try:
                alert["instance_id_values"] = [i for i in ast.literal_eval(alert["monitor_instance_id"])]
            except Exception as e:
                alert["instance_id_values"] = [alert["monitor_instance_id"]]
            # 在 results 字典中添加完整的 policy 和 monitor_instance 信息
            alert["policy"] = MonitorPolicySerializer(policy_dict.get(alert["policy_id"])).data if alert["policy_id"] else None

        # 返回成功响应
        return WebUtils.response_success(dict(count=queryset.count(), results=results))


    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        # 检查是否要更新 status 和其他字段
        updated_data = serializer.validated_data
        if updated_data.get("status") == "closed":
            updated_data["end_event_time"] = datetime.now(timezone.utc)  # 补充时间
            updated_data["operator"] = request.user.username  # 假设操作人从请求中获取

        self.perform_update(serializer)

        # 清理缓存
        if getattr(instance, '_prefetched_objects_cache', None):
            instance._prefetched_objects_cache = {}

        return Response(serializer.data)


class MonitorEventVieSet(viewsets.ViewSet):

    @swagger_auto_schema(
        operation_description="查询告警事件",
        manual_parameters=[
            openapi.Parameter("alert_id", openapi.IN_PATH, description="告警id", type=openapi.TYPE_INTEGER, required=True),
            openapi.Parameter("page", openapi.IN_QUERY, description="页码", type=openapi.TYPE_INTEGER, required=False),
            openapi.Parameter("page_size", openapi.IN_QUERY, description="每页数量", type=openapi.TYPE_INTEGER, required=False),
        ],
    )
    @action(methods=['get'], detail=False, url_path='query/(?P<alert_id>[^/.]+)')
    def get_events(self, request, alert_id):
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 10))
        alert_obj = MonitorAlert.objects.get(id=alert_id)
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
            events = q_set[(page - 1) * page_size: page * page_size]
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

    @swagger_auto_schema(
        operation_description="查询告警最新事件的原始数据",
        manual_parameters=[
            openapi.Parameter("alert_id", openapi.IN_PATH, description="告警id", type=openapi.TYPE_INTEGER, required=True),
        ],
    )
    @action(methods=['get'], detail=False, url_path='raw_data/(?P<alert_id>[^/.]+)')
    def get_raw_data(self, request, alert_id):
        alert_obj = MonitorAlert.objects.get(id=alert_id)
        event_obj = MonitorEvent.objects.filter(policy_id=alert_obj.policy_id, monitor_instance_id=alert_obj.monitor_instance_id).order_by("-created_at").first()
        raw_data = MonitorEventRawData.objects.filter(event_id=event_obj.id).first()
        return WebUtils.response_success(raw_data.data if raw_data else {})


class MonitorAlertMetricSnapshotViewSet(viewsets.ViewSet):
    """告警指标快照视图集"""

    @swagger_auto_schema(
        operation_description="查询告警指标快照",
        manual_parameters=[
            openapi.Parameter("alert_id", openapi.IN_PATH, description="告警ID", type=openapi.TYPE_INTEGER, required=True),
            openapi.Parameter("page", openapi.IN_QUERY, description="页码", type=openapi.TYPE_INTEGER, required=False),
            openapi.Parameter("page_size", openapi.IN_QUERY, description="每页数量", type=openapi.TYPE_INTEGER, required=False),
        ],
        responses={
            200: openapi.Response(
                description="成功",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'count': openapi.Schema(type=openapi.TYPE_INTEGER, description='总数量'),
                        'results': openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(type=openapi.TYPE_OBJECT),
                            description='快照数据列表'
                        )
                    }
                )
            ),
            404: openapi.Response(description="告警不存在")
        }
    )
    @action(methods=['get'], detail=False, url_path='query/(?P<alert_id>[^/.]+)')
    def get_snapshots(self, request, alert_id):
        """根据告警ID查询指标快照数据"""
        try:
            # 1. 根据告警ID获取告警对象
            alert_obj = MonitorAlert.objects.get(id=alert_id)
        except MonitorAlert.DoesNotExist:
            return WebUtils.response_error("告警不存在", status_code=404)

        # 2. 构建查询条件 - 根据告警ID以及告警的开始结束时间
        snapshot_query = {
            'alert_id': alert_obj.id,
            'snapshot_time__gte': alert_obj.start_event_time,
        }

        # 如果告警已结束，添加结束时间过滤条件
        if alert_obj.end_event_time:
            snapshot_query['snapshot_time__lte'] = alert_obj.end_event_time

        # 3. 查询指标快照数据
        queryset = MonitorAlertMetricSnapshot.objects.filter(**snapshot_query).order_by('snapshot_time')

        # 4. 分页处理
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 10))

        if page_size == -1:
            # 返回所有数据
            snapshots = queryset
        else:
            # 分页返回
            start = (page - 1) * page_size
            end = start + page_size
            snapshots = queryset[start:end]

        # 5. 序列化数据
        serializer = MonitorAlertMetricSnapshotSerializer(snapshots, many=True)

        return WebUtils.response_success({
            'count': queryset.count(),
            'results': serializer.data,
            'alert_info': {
                'id': alert_obj.id,
                'policy_id': alert_obj.policy_id,
                'monitor_instance_id': alert_obj.monitor_instance_id,
                'start_event_time': alert_obj.start_event_time,
                'end_event_time': alert_obj.end_event_time,
                'status': alert_obj.status
            }
        })
