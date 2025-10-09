import json
from datetime import timedelta

from django_celery_beat.models import PeriodicTask, CrontabSchedule
from rest_framework import viewsets
from rest_framework.decorators import action
from django.db import models

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.utils.permission_utils import get_permission_rules, get_permissions_rules, permission_filter, check_instance_permission
from apps.core.utils.web_utils import WebUtils
from apps.log.constants import POLICY_MODULE, DEFAULT_PERMISSION, ALERT_STATUS_NEW, ALERT_STATUS_CLOSED
from apps.log.filters.policy import PolicyFilter, AlertFilter, EventFilter, EventRawDataFilter
from apps.log.models.policy import Policy, Alert, Event, EventRawData
from apps.log.serializers.policy import PolicySerializer, AlertSerializer, EventSerializer, EventRawDataSerializer
from config.drf.pagination import CustomPageNumberPagination


class PolicyViewSet(viewsets.ModelViewSet):
    queryset = Policy.objects.all()
    serializer_class = PolicySerializer
    filterset_class = PolicyFilter
    pagination_class = CustomPageNumberPagination

    def list(self, request, *args, **kwargs):
        collect_type_id = request.query_params.get('collect_type', None)

        # 获取权限规则
        permission = get_permission_rules(
            request.user,
            request.COOKIES.get("current_team"),
            "log",
            f"{POLICY_MODULE}.{collect_type_id}",
        )

        # 应用权限过滤
        base_qs = permission_filter(
            Policy,
            permission,
            team_key="policyorganization__organization__in",
            id_key="id__in"
        )

        # 只需要按采集类型过滤（移除冗余的组织过滤）
        qs = base_qs.filter(collect_type_id=collect_type_id)

        queryset = self.filter_queryset(qs)
        queryset = queryset.distinct().select_related('collect_type')

        # 获取分页参数
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 10))

        # 计算分页的起始位置
        start = (page - 1) * page_size
        end = start + page_size

        # 获取当前页的数据
        page_data = queryset[start:end]

        # 执行序列化
        serializer = self.get_serializer(page_data, many=True)
        results = serializer.data

        # 添加权限信息到每个策略实例
        policy_permission_map = {i["id"]: i["permission"] for i in permission.get("instance", [])}

        for policy_info in results:
            if policy_info['id'] in policy_permission_map:
                policy_info['permission'] = policy_permission_map[policy_info['id']]
            else:
                policy_info['permission'] = DEFAULT_PERMISSION

        return WebUtils.response_success(dict(count=queryset.count(), items=results))

    def create(self, request, *args, **kwargs):
        # 补充创建人
        request.data['created_by'] = request.user.username
        request.data['updated_by'] = request.user.username

        # 提取organizations数据，不传给serializer
        organizations = request.data.pop('organizations', [])
        if not organizations:
            return WebUtils.response_error("organizations is required")

        response = super().create(request, *args, **kwargs)
        policy_id = response.data['id']

        # 创建组织关联
        from apps.log.models.policy import PolicyOrganization
        PolicyOrganization.objects.bulk_create(
            [PolicyOrganization(policy_id=policy_id, organization=org_id) for org_id in organizations],
            ignore_conflicts=True
        )

        schedule = request.data.get('schedule')
        if schedule:
            self.update_or_create_task(policy_id, schedule)
        return response

    def update(self, request, *args, **kwargs):
        # 补充更新人
        request.data['updated_by'] = request.user.username

        # 提取organizations数据，不传给serializer
        # 注意：只有当请求中明确包含organizations时才进行更新
        organizations = None
        if 'organizations' in request.data:
            organizations = request.data.pop('organizations', [])

        response = super().update(request, *args, **kwargs)
        policy_id = kwargs['pk']

        # 只有当明确传递了organizations参数时才更新组织关联
        if organizations is not None:
            from apps.log.models.policy import PolicyOrganization
            # 清除旧的组织关联
            PolicyOrganization.objects.filter(policy_id=policy_id).delete()
            # 添加新的组织关联
            PolicyOrganization.objects.bulk_create(
                [PolicyOrganization(policy_id=policy_id, organization=org_id) for org_id in organizations],
                ignore_conflicts=True
            )

        schedule = request.data.get('schedule')
        if schedule:
            self.update_or_create_task(policy_id, schedule)
        return response

    def partial_update(self, request, *args, **kwargs):
        # 补充更新人
        request.data['updated_by'] = request.user.username

        # 提取organizations数据，不传给serializer
        # 注意：只有当请求中明确包含organizations时才进行更新
        organizations = None
        if 'organizations' in request.data:
            organizations = request.data.pop('organizations')

        response = super().partial_update(request, *args, **kwargs)
        policy_id = kwargs['pk']

        # 只有当明确传递了organizations参数时才更新组织关联
        if organizations is not None:
            from apps.log.models.policy import PolicyOrganization
            # 清除旧的组织关联
            PolicyOrganization.objects.filter(policy_id=policy_id).delete()
            # 添加新的组织关联
            PolicyOrganization.objects.bulk_create(
                [PolicyOrganization(policy_id=policy_id, organization=org_id) for org_id in organizations],
                ignore_conflicts=True
            )

        schedule = request.data.get('schedule')
        if schedule:
            self.update_or_create_task(policy_id, schedule)
        return response

    def destroy(self, request, *args, **kwargs):
        policy_id = kwargs['pk']
        # 删除相关的定时任务
        PeriodicTask.objects.filter(name=f'log_policy_task_{policy_id}').delete()
        return super().destroy(request, *args, **kwargs)

    def format_crontab(self, schedule):
        """
        将 schedule 格式化为 CrontabSchedule 实例
        """
        schedule_type = schedule.get('type')
        value = schedule.get('value')

        if schedule_type == 'min':
            return CrontabSchedule.objects.get_or_create(
                minute=f'*/{value}', hour='*', day_of_month='*', month_of_year='*', day_of_week='*'
            )[0]
        elif schedule_type == 'hour':
            return CrontabSchedule.objects.get_or_create(
                minute=0, hour=f'*/{value}', day_of_month='*', month_of_year='*', day_of_week='*'
            )[0]
        elif schedule_type == 'day':
            return CrontabSchedule.objects.get_or_create(
                minute=0, hour=0, day_of_month=f'*/{value}', month_of_year='*', day_of_week='*'
            )[0]
        else:
            raise BaseAppException('Invalid schedule type')

    def update_or_create_task(self, policy_id, schedule):
        task_name = f'log_policy_task_{policy_id}'

        # 删除旧的定时任务
        PeriodicTask.objects.filter(name=task_name).delete()

        # 解析 schedule，并创建相应的调度
        format_crontab = self.format_crontab(schedule)
        # 创建新的 PeriodicTask
        PeriodicTask.objects.create(
            name=task_name,
            task='apps.log.tasks.policy.scan_log_policy_task',
            args=json.dumps([policy_id]),
            crontab=format_crontab,
            enabled=True
        )

    @action(methods=['post'], detail=True, url_path='enable')
    def enable(self, request, pk=None):
        policy = self.get_object()
        enabled = request.data.get('enabled', True)

        task_name = f'log_policy_task_{pk}'
        try:
            task = PeriodicTask.objects.get(name=task_name)
            task.enabled = enabled
            task.save()
            return WebUtils.response_success({"enabled": enabled})
        except PeriodicTask.DoesNotExist:
            return WebUtils.response_error("策略对应的定时任务不存在")


class AlertViewSet(viewsets.ModelViewSet):
    queryset = Alert.objects.select_related('policy', 'collect_type').order_by('-created_at')
    serializer_class = AlertSerializer
    filterset_class = AlertFilter
    pagination_class = CustomPageNumberPagination

    def _get_all_accessible_policy_ids(self, request):
        """
        获取当前用户所有有权限的策略ID
        优化版本：参考监控模块的权限判断逻辑，减少SQL查询次数
        """
        current_team = request.COOKIES.get("current_team")
        if not current_team:
            return []

        # 获取所有采集类型下policy模块的权限规则
        permissions_result = get_permissions_rules(
            request.user,
            current_team,
            "log",
            POLICY_MODULE,
        )

        policy_permissions = permissions_result.get("data", {})
        cur_team = permissions_result.get("team", [])

        if not policy_permissions:
            return []

        # 一次性获取所有策略及其关联组织，减少SQL查询
        all_policies = Policy.objects.select_related('collect_type').prefetch_related(
            'policyorganization_set'
        ).all()

        accessible_policy_ids = []

        # 遍历所有策略，在内存中进行权限检查（使用通用权限检查函数）
        for policy_obj in all_policies:
            collect_type_id = str(policy_obj.collect_type_id)
            policy_id = policy_obj.id

            # 获取策略关联的组织
            teams = {org.organization for org in policy_obj.policyorganization_set.all()}

            # 使用通用权限检查函数
            if check_instance_permission(collect_type_id, policy_id, teams, policy_permissions, cur_team):
                accessible_policy_ids.append(policy_id)

        return accessible_policy_ids

    def list(self, request, *args, **kwargs):
        """
        告警列表查询

        支持两种查询模式：
        1. 传入collect_type：查询特定采集类型的告警
        2. 不传collect_type：查询当前用户所有有权限的采集类型的告警
        """
        collect_type_id = request.query_params.get('collect_type', None)

        if collect_type_id:
            # 查询特定采集类型的告警
            permission = get_permission_rules(
                request.user,
                request.COOKIES.get("current_team"),
                "log",
                f"{POLICY_MODULE}.{collect_type_id}",
            )

            # 应用权限过滤
            policy_qs = permission_filter(
                Policy,
                permission,
                team_key="policyorganization__organization__in",
                id_key="id__in"
            )
            policy_qs = policy_qs.filter(
                collect_type_id=collect_type_id,
                policyorganization__organization=request.COOKIES.get("current_team")
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
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 10))

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

    @action(methods=['get'], detail=False, url_path='all')
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
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 10))

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

    @action(methods=['post'], detail=True, url_path='closed')
    def closed(self, request, pk=None):
        alert = self.get_object()
        operator = request.user.username

        alert.status = ALERT_STATUS_CLOSED
        alert.operator = operator
        alert.save()

        return WebUtils.response_success({"status": ALERT_STATUS_CLOSED, "operator": operator})

    @action(methods=['get'], detail=False, url_path='last_event')
    def get_last_event(self, request):
        """
        获取最新的事件
        """
        alert_id = request.query_params.get('alert_id')
        if not alert_id:
            return WebUtils.response_error("缺少告警ID参数")

        event = Event.objects.filter(alert_id=alert_id).order_by('-event_time').first()
        if not event:
            return WebUtils.response_error("未找到相关事件")

        event_raw_data = EventRawData.objects.filter(event_id=event.id).first()

        data = {
            "event": EventSerializer(event).data,
            "raw_data": EventRawDataSerializer(event_raw_data).data if event_raw_data else None
        }

        return WebUtils.response_success(data)

    @action(methods=['get'], detail=False, url_path='stats')
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
        collect_type_id = request.query_params.get('collect_type', None)

        if collect_type_id:
            # 统计特定采集类型的告警
            permission = get_permission_rules(
                request.user,
                request.COOKIES.get("current_team"),
                "log",
                f"{POLICY_MODULE}.{collect_type_id}",
            )

            # 先过滤出有权限的Policy
            policy_qs = permission_filter(
                Policy,
                permission,
                team_key="policyorganization__organization__in",
                id_key="id__in"
            )
            policy_qs = policy_qs.filter(
                collect_type_id=collect_type_id,
                policyorganization__organization=request.COOKIES.get("current_team")
            ).distinct()

            # 获取有权限的policy_ids
            policy_ids = list(policy_qs.values_list("id", flat=True))
        else:
            # 统计所有有权限的采集类型的告警（使用优化后的统一方法）
            policy_ids = self._get_all_accessible_policy_ids(request)

            if not policy_ids:
                return WebUtils.response_success({
                    "total": 0,
                    "status": request.query_params.get('status', ALERT_STATUS_NEW),
                    "time_range": {"start": None, "end": None},
                    "step_minutes": int(request.query_params.get('step', 60)),
                    "time_series": []
                })

        # 基于policy权限过滤告警（与list接口保持一致）
        queryset = self.filter_queryset(self.get_queryset())
        queryset = queryset.filter(policy_id__in=policy_ids).distinct()

        # 获取参数
        status = request.query_params.get('status', ALERT_STATUS_NEW)
        step_minutes = int(request.query_params.get('step', 60))

        # 按状态过滤
        queryset = queryset.filter(status=status)

        # 生成时间序列统计
        time_series_data, time_range = self._get_step_based_stats(queryset, step_minutes)

        return WebUtils.response_success({
            "total": queryset.count(),
            "status": status,
            "time_range": time_range,
            "step_minutes": step_minutes,
            "time_series": time_series_data
        })

    def _get_step_based_stats(self, queryset, step_minutes):
        """基于step动态分割时间区间进行统计，按告警级别分组"""
        # 获取数据的时间范围
        time_range_data = queryset.aggregate(
            min_time=models.Min('created_at'),
            max_time=models.Max('created_at')
        )

        min_time = time_range_data['min_time']
        max_time = time_range_data['max_time']

        if not min_time or not max_time:
            return [], {"start": None, "end": None}

        # 时间范围信息
        time_range = {
            "start": min_time.isoformat(),
            "end": max_time.isoformat()
        }

        # 生成时间区间
        step_delta = timedelta(minutes=step_minutes)
        current_time = min_time
        time_intervals = []

        # 修复：确保包含最后一个时间点的数据
        while current_time <= max_time:
            interval_end = min(current_time + step_delta, max_time + timedelta(microseconds=1))
            time_intervals.append({
                'start': current_time,
                'end': interval_end
            })
            current_time += step_delta
            
            # 如果下一个区间的开始时间已经超过最大时间，则停止
            if current_time > max_time:
                break

        # 关键优化：一次性获取所有数据，然后在Python中分组
        # 只执行一次数据库查询
        all_alerts = list(queryset.values('created_at', 'level'))

        # 在Python中按时间区间分组统计
        result = []
        for interval in time_intervals:
            # 在内存中过滤当前时间区间的数据
            interval_alerts = [
                alert for alert in all_alerts
                if interval['start'] <= alert['created_at'] < interval['end']
            ]

            # 在内存中按级别统计
            level_data = {}
            for alert in interval_alerts:
                level = alert['level']
                level_data[level] = level_data.get(level, 0) + 1

            total_count = sum(level_data.values())

            result.append({
                'time_start': interval['start'].isoformat(),
                'time_end': interval['end'].isoformat(),
                'total': total_count,
                'levels': level_data
            })

        return result, time_range


class EventViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Event.objects.all()
    serializer_class = EventSerializer
    filterset_class = EventFilter
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        return Event.objects.select_related('policy', 'alert').order_by('-event_time')


class EventRawDataViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = EventRawData.objects.all()
    serializer_class = EventRawDataSerializer
    filterset_class = EventRawDataFilter
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        return EventRawData.objects.select_related('event').order_by('-event__event_time', '-id')

    @action(methods=['get'], detail=False, url_path='by_event_id')
    def rawdata_list_by_event_id(self, request):
        """
        根据事件ID获取原始数据
        
        由于每个事件只对应一条原始数据记录，所以直接返回对应的数据，无需分页

        URL: /api/event-raw-data/by_event_id/?event_id=xxx
        """
        event_id = request.query_params.get('event_id')
        if not event_id:
            return WebUtils.response_error("缺少事件ID参数")

        try:
            # 直接获取对应的原始数据记录
            event_raw_data = EventRawData.objects.select_related('event').get(event_id=event_id)
            serializer = self.get_serializer(event_raw_data)
            return WebUtils.response_success(serializer.data)
        except EventRawData.DoesNotExist:
            return WebUtils.response_error("未找到对应的原始数据")